You are a Python expert programmer

You write a sample Python converter script conver_result.py that

- reads the file "sample_result.json"
- extracts the first content item of the JSON (lists of dicts)
- provide converters of the saved for Form DATA to plain text (in a nice way), PDF, HTML and Markdown
- the form definition of the data is stored in survey-form-form.json and can be used for hints regard the
  structure of the saved data, keys etc

- create an output folder "output"
- store all output formats as dedictaed files inside "output" along with the poll_id as prefix of each file

Hint: the form data may contain b64 encoded files and images

use "uv" for prototyping. uv is already installed. Add requirements as inline requirements according to the latest "uvx" documentation
