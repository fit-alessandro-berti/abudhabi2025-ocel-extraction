PYTHON ?= .venv/bin/python

.PHONY: extract validate analyze test reproduce fetch package
extract:
	$(PYTHON) scripts/extract_ocel.py
validate:
	$(PYTHON) scripts/validate_ocel.py
analyze:
	$(PYTHON) scripts/analyze_ocel.py
test:
	$(PYTHON) -m unittest discover -s tests -v
package:
	$(PYTHON) scripts/package_release.py
reproduce:
	$(PYTHON) scripts/extract_ocel.py
	$(PYTHON) scripts/validate_ocel.py
	$(PYTHON) -m unittest discover -s tests -v
	$(PYTHON) scripts/analyze_ocel.py
	$(PYTHON) scripts/package_release.py
fetch:
	$(PYTHON) scripts/fetch_sources.py
