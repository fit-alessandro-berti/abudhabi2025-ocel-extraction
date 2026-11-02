PYTHON ?= .venv/bin/python

.PHONY: extract validate analyze test reproduce fetch
extract:
	$(PYTHON) scripts/extract_ocel.py
validate:
	$(PYTHON) scripts/validate_ocel.py
analyze:
	$(PYTHON) scripts/analyze_ocel.py
test:
	$(PYTHON) -m unittest discover -s tests -v
reproduce:
	$(PYTHON) scripts/extract_ocel.py
	$(PYTHON) scripts/validate_ocel.py
	$(PYTHON) -m unittest discover -s tests -v
	$(PYTHON) scripts/analyze_ocel.py
fetch:
	$(PYTHON) scripts/fetch_sources.py
