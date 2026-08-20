"""Starter code for the LLM phishing-evidence faithfulness project.

Pipeline order (see docs/SPEC.md):

    download  ->  preprocess  ->  citation_view  ->  prompts
                                                       |
                                                     (model)
                                                       |
                                        parse -> grounding -> interventions
"""

__version__ = "0.1.0"
