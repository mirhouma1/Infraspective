# CSA S16 Flexure Calculator

## Overview
A Streamlit-based structural engineering calculator for checking W-section steel beams per CSA S16 (Canadian steel design standard). The app performs:
- Section classification per CSA S16 Table 2 (Class 1-4)
- Laterally supported moment resistance (Mr) calculations
- Demand/capacity checks against factored moments

## Project Structure
```
├── app.py                 # Main Streamlit application
├── data/
│   └── w_sections.csv     # W-section database (Canadian sections)
├── .streamlit/
│   └── config.toml        # Streamlit server configuration
└── attached_assets/       # Original source files
```

## Key Features
- **Section Selection**: Search and select from 100+ Canadian W-sections
- **Classification**: Automatic flange/web slenderness classification per Table 2
- **Moment Resistance**: Calculates Mr using plastic (Zx) or elastic (Sx) section modulus
- **Demand Check**: Optional pass/fail check against factored moment demand

## Technical Details

### Section Classification (CSA S16 Table 2)
- Flange outstand slenderness: (b/2)/tf
- Web slenderness: h/w where h = d - 2k (clear web depth)
- Limits based on Fy: 145/sqrt(Fy), 170/sqrt(Fy), 200/sqrt(Fy) for flanges

### Moment Resistance
- Class 1-2: Mr = φb × Zx × Fy (plastic)
- Class 3: Mr = φb × Sx × Fy (elastic)
- φb = 0.9 (resistance factor for bending)

### Data Format
CSV columns include: Designation, Depth d, Flange Width b, Flange Thickness t, Web Thickness w, Distance k, Zx, Sx, and more.

## Running the App
```bash
streamlit run app.py --server.port 5000
```

## Recent Changes
- 2025-12-25: Initial implementation with section classification, Mr calculation, and demand checking
- 2025-12-25: Fixed web slenderness calculation to use CSA S16 clear web depth (d - 2k)
