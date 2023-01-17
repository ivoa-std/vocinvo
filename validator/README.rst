=========================
IVOA Vocabulary validator
=========================

This is a program that exercises the IVOA vocabulary repository
(https://www.ivoa.net/rdf) for the MUST-requirements in the spec,
as far as they appeared validatable.

It comes as a one-file python script.  Install the dependencies
(see the module docstring) and then just run::

  python vocvalidator.py

to validate all Vocabularies 2-compliant vocabularies (connects to
github to get a list of these) or

  python vocvalidator.py <uri> [<uri>...]

to only validate one or more specific vocabularies.
