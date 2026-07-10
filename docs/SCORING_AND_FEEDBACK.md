# Scoring and Feedback Strategy

## Scoring strategy

The MVP does not claim that fixed weights are the final intelligence system. It uses an explainable baseline while UGFS collects human-labeled examples.

Long-term approach:

1. LLM extracts structured information.
2. Feature extractor creates numeric and categorical indicators.
3. Baseline scoring produces initial risk/opportunity scores.
4. Human team corrects Excel.
5. Corrected rows become training data.
6. Once enough corrected examples exist, train regression models.

## Why no ML from day one?

Machine learning requires enough labeled examples. The first pilot may only contain 10 PDFs, which is useful for validation but too small for reliable regression.

## Feedback memory

The model is not retrained. Corrections are converted into rules/examples and injected into future prompts.

Example:

```json
{
  "type_erreur": "Erreur de classification",
  "prediction_ia": "Modification statutaire",
  "correction_humaine": "Augmentation de capital",
  "regle_apprise": "Si le texte mentionne augmentation du capital social, classer en Capital / Augmentation de capital."
}
```
