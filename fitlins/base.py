import os
from os import path as op
from functools import reduce
import numpy as np
import pandas as pd
import nibabel as nb
import nilearn.image as nli
from nistats import design_matrix as dm
from nistats import first_level_model as level1, second_level_model as level2

import pkg_resources as pkgr

from grabbit import merge_layouts
from bids import grabbids
from bids.analysis import base as ba


def dict_intersection(dict1, dict2):
    return {k: v for k, v in dict1.items() if dict2.get(k) == v}


def snake_to_camel(string):
    words = string.split('_')
    return words[0] + ''.join(word.title() for word in words[1:])


def init(model_fname, bids_dir, preproc_dir):
    orig_layout = grabbids.BIDSLayout(bids_dir)
    prep_layout = grabbids.BIDSLayout(preproc_dir, extensions=['derivatives'])
    analysis = ba.Analysis(model=model_fname,
                           layout=merge_layouts([orig_layout, prep_layout]))
    analysis.setup()
    return analysis


def first_level(analysis, block, deriv_dir):
    out_imgs = {}
    for paradigm, ents in block.get_design_matrix():
        preproc_files = analysis.layout.get(type='preproc', space='MNI152NLin2009cAsym',
                                            **ents)
        if len(preproc_files) != 1:
            print(preproc_files)
            raise ValueError("Too many potential PREPROC files")

        fname = preproc_files[0].filename

        # confounds_file = analysis.layout.get(type='confounds', **ents)[0]
        # confounds = pd.read_csv(confounds_file.filename, sep="\t", na_values="n/a").fillna(0)
        # names = [col for col in confounds.columns
        #          if col.startswith('NonSteadyStateOutlier') or
        #          col in block.model['variables']]
        img = nb.load(fname)
        TR = img.header.get_zooms()[3]
        vols = img.shape[3]

        mat = dm.make_design_matrix(np.arange(vols) * TR,
                                    paradigm.rename(columns={'condition': 'trial_type'}),
                                    drift_model=None,
                                    # add_regs=confounds[names],
                                    # add_reg_names=names,
                                    )

        out_dir = deriv_dir
        if 'subject' in ents:
            out_dir = op.join(out_dir, 'sub-' + ents['subject'])
        if 'session' in ents:
            out_dir = op.join(out_dir, 'ses-' + ents['session'])

        os.makedirs(out_dir, exist_ok=True)

        base = op.basename(fname)
        design_fname = op.join(out_dir, base.replace('_preproc.nii.gz', '_design.tsv'))

        mat.to_csv(design_fname, sep='\t')

        brainmask = analysis.layout.get(type='brainmask', **ents)[0]
        fmri_glm = None

        for contrast in block.contrasts:
            stat_fname = op.join(out_dir,
                                 base.replace('_preproc.nii.gz',
                                              '_contrast-{}_stat.nii.gz'.format(
                                                  snake_to_camel(contrast['name']))))
            out_imgs.setdefault(contrast['name'], []).append(stat_fname)

            if op.exists(stat_fname):
                continue

            if fmri_glm is None:
                fmri_glm = level1.FirstLevelModel(mask=brainmask.filename)
                fmri_glm.fit(fname, design_matrices=mat)

            indices = [mat.columns.get_loc(cond)
                       for cond in contrast['condition_list']]

            weights = np.zeros(len(mat.columns))
            weights[indices] = contrast['weights']

            stat = fmri_glm.compute_contrast(weights, {'T': 't', 'F': 'F'}[contrast['type']])
            stat.to_filename(stat_fname)

    return out_imgs


def second_level(analysis, block, deriv_dir, mapping=None):
    fl_layout = grabbids.BIDSLayout(
        deriv_dir,
        extensions=['derivatives',
                    pkgr.resource_filename('fitlins', 'data/fitlins.json')])
    fl_layout.path_patterns.append(
        '[sub-{subject}/][ses-{session}/][sub-{subject}][_ses-{session}]_task-{task}_bold'
        '[_space-{space}][_contrast-{contrast}]_{type}.nii.gz')

    if mapping is None:
        mapping = {}
    for xform in block.transformations:
        if xform['name'] == 'split':
            for in_col in xform['input']:
                by = xform['by']
                splitter = {'session': analysis.layout.get_sessions,
                            'subject': analysis.layout.get_subjects}[by]()
                # Update mapping
                for var in splitter:
                    mapping['{}.{}'.format(var, in_col)] = (in_col, {by: var})
        else:
            raise ValueError("Unhandled transformation: " + xform['name'])

    for i, (_, ents) in enumerate(block.get_design_matrix()):
        fmri_glm = level2.SecondLevelModel()

        for contrast in block.contrasts:
            data = []
            for condition in contrast['condition_list']:
                real_cond, mapped_ents = mapping.get(condition, (condition, {}))
                matches = fl_layout.get(
                    type='stat',
                    contrast=snake_to_camel(real_cond),
                    **ents, **analysis.selectors, **mapped_ents)
                data.extend(match.filename for match in matches)

            out_ents = reduce(dict_intersection,
                              map(fl_layout.parse_entities, data))
            out_ents['contrast'] = snake_to_camel(contrast['name'])

            stat_fname = op.join(deriv_dir,
                                 fl_layout.build_path(out_ents, strict=True))

            if op.exists(stat_fname):
                continue

            cols = {'intercept': np.ones(len(data))}
            cname = 'intercept'
            if not np.allclose(contrast['weights'], 1):
                cname = contrast['name']
                cols[cname] = contrast['weights']

            paradigm = pd.DataFrame(cols)

            fmri_glm.fit(data, design_matrix=paradigm)
            stat = fmri_glm.compute_contrast(
                cname,
                second_level_stat_type={'T': 't', 'F': 'F'}[contrast['type']])
            stat.to_filename(stat_fname)

    return mapping


def ttest(model_fname, bids_dir, preproc_dir, deriv_dir, session=None, task=None, space=None):

    varsel = {key: val
              for key, val in (('session', session), ('task', task)) if val}

    analysis = ba.Analysis([bids_dir, preproc_dir], model_fname, **varsel)
    block = analysis.blocks[0]
    # analysis.setup()
    analysis.manager.load()
    block.setup(analysis.manager, None)

    varsel.update(analysis.model['input'])

    if space:
        varsel.setdefault('space', space)

    prep_layout = grabbids.BIDSLayout(preproc_dir, extensions=['derivatives'])
    brainmasks = nli.concat_imgs(img.filename
                                 for img in prep_layout.get(type='brainmask', **varsel))
    brainmask = nli.math_img('img.any(axis=3)', img=brainmasks)
    fmri_glm = level2.SecondLevelModel(mask=brainmask)

    fl_layout = grabbids.BIDSLayout(deriv_dir, extensions=['derivatives'])
    for contrast in block.contrasts:
        # No contrast selector at this point
        stat_files = [f for f in fl_layout.get(type='stat', **varsel)
                      if 'contrast-{}'.format(snake_to_camel(contrast['name'])) in f.filename]

        basename = os.path.basename(stat_files[0].filename).split('_', 1)[1]

        paradigm = pd.DataFrame({'intercept': np.ones(len(stat_files))})
        fmri_glm.fit([img.filename for img in stat_files], design_matrix=paradigm)
        stat = fmri_glm.compute_contrast(second_level_stat_type='t')
        stat.to_filename(os.path.join(deriv_dir, basename))


def prep_model(model_fname, bids_dir, preproc_dir, deriv_dir,
               subject=None, session=None, task=None, space=None):
    from bids.analysis import Analysis

    varsel = {key: val
              for key, val in (('subject', subject), ('session', session), ('task', task)) if val}
    imgsel = varsel.copy()
    if space:
        imgsel['space'] = space

    model = Analysis([bids_dir, preproc_dir], model_fname,
                     img_selectors=imgsel, var_selectors=varsel)


def hrf_convolve(design_matrix, hrf_vars, hrf_model='glover'):
    new_matrix = design_matrix.copy()
    hrf_cols = design_matrix[hrf_vars].copy()
