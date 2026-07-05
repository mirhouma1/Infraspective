---
name: Flexure Class 4 effective-width boundary & pyarrow noise
description: Two non-obvious flexure facts — Class 4 Se effective-width limits must match Class 3 classification limits, and a harmless recurring pyarrow traceback.
---

# Class 4 effective-width λ_r must equal the Class 3 classification limit
In `app.py`, the Class 4 effective-section-modulus (Se) path (`flange_lambda_r`,
`web_lambda_r`, used by `effective_flange_width` / `effective_web_height` /
`compute_Se_CSA`) uses a limiting slenderness λ_r to decide when an element is reduced.

**Rule:** λ_r MUST equal the Class 3/4 boundary used in classification —
flange = 200/√Fy, web (I-section, flexure, Cf=0) = 1700/√Fy.

**Why:** an element only becomes Class 4 (needs an effective-width reduction) once it
exceeds the Class 3 limit. If λ_r is smaller than the Class 3 limit, the Se path reduces
webs/flanges that classification still treats as fully effective — the two halves of the
flexure calc disagree. A prior version wrongly used web λ_r = 525/√Fy (an HSS-wall value)
and flange λ_r = 170/√Fy (the Class 2 limit), both inconsistent.

**How to apply:** if you ever change the Table 2 classification limits (flange 145/170/200,
web 1100/1700/1900 ÷√Fy), update these λ_r functions in lockstep so the Class 3 boundary
stays identical in both places.

# Harmless pyarrow ArrowTypeError on the flexure page
Rendering the flexure page's slenderness/classification `st.dataframe` emits repeated
`pyarrow.lib.ArrowTypeError` / `convert_pandas_df_to_arrow_bytes` tracebacks in the
Streamlit server logs (mixed object-typed "Value" column). Streamlit falls back and the
UI renders correctly — this is pre-existing, cosmetic log noise, NOT a regression.

**Why it matters:** automated UI test agents flag this as a "python traceback" and report a
false failure even when the feature under test rendered fine. Treat it as expected noise;
only a traceback that actually breaks rendering is a real failure.
