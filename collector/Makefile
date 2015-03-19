# Makefile for testing the Cluster-Insight data collector.
#
# Do not use this Makefile for building the Cluster-Insight data collector.
# Please read Dockerfile for details on building this service.
PYTHON="python"

test: test_utilities test_cache test_collector

test_cache: simple_cache_test.py
	$(PYTHON) $^

test_utilities: utilities_test.py
	$(PYTHON) $^

test_collector: collector_test.py
	$(PYTHON) $^
