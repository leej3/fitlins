<?xml version="1.0" encoding="utf-8" ?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en" lang="en">
<head>
<meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
<title>Fitlins - {{ level }}-level report</title>
<style type="text/css">
.sub-report-title {}
.run-title {}
.elem-title {}
.elem-desc {}
.elem-filename {}
.ortho {
    width: 90%;   
}
</style>
</head>
<body>
    <div id="summary">
        <h1 class="sub-report-title">Summary</h1>
        <ul class="elem-desc">
            <li>Subject ID: {{ subject_id }}</ul>
            <li>Dataset: {{ dataset }}</ul>
            <li>Model: {{ model_name }}</ul>
        </ul>
    </div>
    <div id="model">
        <h1 class="sub-report-title">Model</h1>
        <h2>Design matrix</h3>
        <img src="{{ design_matrix_svg }}" />
        <h2>Contrasts</h3>
        <img src="{{ contrasts_svg }}" />
        <h2>Correlation matrix</h3>
        <img src="{{ correlation_matrix_svg }}" />
    </div>
    {% if contrasts %}
    <div id="contrasts">
        <h1 class="sub-report-title">Contrasts</h1>
        {% for contrast in contrasts %}
        <h2>{{ contrast.name }}</h2>
        <img class="ortho" src="{{ contrast.image_file }}" />
        {% endfor %}
    </div>
    {% endif %}
    {% if estimates %}
    <div id="estimates">
        <h1 class="sub-report-title">Estimates</h1>
        {% for estimate in estimates %}
        <h2>{{ estimate.name }}</h2>
        <img class="ortho" src="{{ estimate.image_file }}" />
        {% endfor %}
    </div>
    {% endif %}
    <div id="about">
        <h1 class="sub-report-title">About</h1>
        <ul>
            <li>Fitlins version: {{ version }}</li>
            <li>Fitlins command: <tt>{{ command }}</tt></li>
            <li>Date processed: {{ timestamp }}</li>
        </ul>
    </div>
</body>
</html>
