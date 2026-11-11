# Reference labels

The Regulatory Safety lens checks expectedness (listedness) against a reference label
only when one is loaded here. Without a label, expectedness is reported as
"Unknown / Label Not Available" — Vigio never relies on the model's memory of a label.

Add one plain-text file per product, named by generic name in lower case:

    labels/warfarin.txt
    labels/pembrolizumab.txt
    labels/metformin.txt

Paste the relevant sections of the current US Prescribing Information (Boxed Warning,
Warnings and Precautions, Adverse Reactions), SmPC section 4.8, or the Investigator's
Brochure reference safety information. Record the label version and date at the top of
the file so the brief can cite it.

Up to 20,000 characters per label are sent to the model. For production, replace this
folder with a versioned label store.
