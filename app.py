# app.py
# Infraspective Solutions - Structural Design Calculators
#
# This is the entry point of the app. It renders the disclaimer gate and
# then the home directory: an accordion of
#
#     service -> standard -> discipline -> calculator
#
# The tree itself lives in _theme.SERVICES and is drawn by
# _theme.render_directory, which also draws the sidebar - one function, so
# the two surfaces cannot drift apart.
#
# The calculator tree itself lives in _theme.CATALOGUE, so adding a
# calculator is one row there and nothing here changes.
#
# ASCII only. Straight quotes only.

from __future__ import annotations

import streamlit as st

from _theme import (apply_theme, render_sidebar_logo, render_footer,
                    gate_disclaimer, render_brand_logo, render_directory)

APP_TITLE = "Infraspective - Structural Design Calculator"
DISCLAIMER_VERSION = "2026-07-29_v3"

DISCLAIMER_MD = """
# INFRASPECTIVE - USER ACCESS AGREEMENT

---

**1. BETA SOFTWARE NOTICE**

Infraspective provides this application for evaluation and optimization purposes. The App is Beta software: features may be incomplete, may change without notice, and may contain errors, including incorrect calculations. By using the App, you acknowledge these limitations and agree that anonymous usage data may be collected to assist in the refinement of the calculation engine.

---

**2. PROFESSIONAL VERIFICATION**

This tool is a calculation aid and does not replace professional engineering judgment. The User is responsible for the independent verification of all outputs in accordance with the laws and professional-practice requirements of their jurisdiction.

All results must be validated by a licensed Professional Engineer in Canada prior to any project application.

The User agrees not to rely on any App output for any project purpose unless and until that output has been independently verified.

The User acknowledges that any use of App outputs without independent verification is done entirely at their own risk.

Use of this App does not create an engineer-client relationship between the User and Infraspective.

---

**3. DATA USAGE & CONSENT**

By using the App, you consent to the collection of anonymous usage data, including technical input parameters, feature usage, session activity, and error reports. No personal information is collected. This data is used exclusively to optimize the software's logic, reliability, and performance during the Beta period. Providing feedback is welcome but not required.

---

**4. LIMITATION OF LIABILITY**

This software is provided "AS IS" and is in a Beta state, meaning it may contain errors, incomplete features, or incorrect calculations.

Infraspective disclaims all warranties regarding the accuracy of the Beta calculations.

The User assumes all risk associated with the use of the App's outputs. Use of this App is entirely at the User's own risk.

To the maximum extent permitted by law, Infraspective shall not be liable for any direct, indirect, incidental, or consequential damages arising from use of the App.

This limitation of liability applies even if the App fails its essential purpose or is found to be in fundamental breach of contract.

No compensation or damages of any kind are payable for errors, omissions, or inaccuracies in the App or its outputs.

---

**5. INDEMNITY**

The User agrees to indemnify, defend, and hold harmless Infraspective from any and all claims, demands, losses, or legal fees (including solicitor-client costs) arising from the User's use of, misuse of, or reliance on the App, whether the claim is made by the User or a third party.

---

**6. GOVERNING LAW & JURISDICTION**

This agreement is governed by the federal laws of Canada and the laws of the Canadian province or territory in which the User resides or practises. Any dispute shall be resolved exclusively in the courts of that jurisdiction.

---

**7. SEVERABILITY**

If any provision of this Agreement is found unenforceable, the remaining provisions shall remain in full force and effect.

---

**8. VERIFICATION ACKNOWLEDGMENT**

Before each use of the App, the User shall affirmatively confirm their agreement below.

The User acknowledges that failure to verify does not transfer liability to Infraspective.

---

*BY USING THIS APP, YOU ACKNOWLEDGE THAT YOU HAVE READ, UNDERSTOOD, AND AGREE TO ALL TERMS ABOVE.*
"""


# ===========================================================
# PAGE SETUP
# ===========================================================

st.set_page_config(page_title="Infraspective - Structural Design "
                              "Calculator",
                   page_icon=":triangular_ruler:", layout="wide")

if st.session_state.get("disclaimer_version") != DISCLAIMER_VERSION:
    st.session_state["accepted_disclaimer"] = False
    st.session_state["disclaimer_version"] = DISCLAIMER_VERSION

apply_theme()
render_sidebar_logo()
render_footer()
gate_disclaimer()


# ===========================================================
# HOME DIRECTORY
# ===========================================================

render_brand_logo()

st.markdown('<p class="ins-grouphead">Services</p>', unsafe_allow_html=True)

render_directory(st, "hm_")
