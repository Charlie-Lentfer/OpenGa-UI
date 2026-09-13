# Deploy OpenGa app V2

The app is already integrated. No additional flowsheet snippet is required.

## Existing V1 repository

1. Keep a backup of V1 or its current commit.
2. Replace the repository's app files with the **contents** of this V2 folder.
   Include `openga_flowsheet/`, `openga_v1/stream_metadata.json` and the hidden
   `.streamlit/config.toml` file.
3. From the repository root, install `requirements.txt`, run `python selftest.py`,
   then `python -m streamlit run app/streamlit_app.py`.
4. Commit and push the files to the branch used by your Streamlit deployment.
   The main file path remains **`app/streamlit_app.py`**.
5. Open Flowsheet and check Image mode. In User mode, change feed assay and
   confirm the diagram changes with the model.

No GitHub repository or cloud app was created or modified during preparation.

## New Streamlit Community Cloud app

Use this structure at the repository root:

```text
requirements.txt
.streamlit/config.toml
app/streamlit_app.py
app/charts.py
openga_v1/                 # include stream_metadata.json
openga_flowsheet/          # complete renderer and component
selftest.py
tests/
```

Create an app in Streamlit Community Cloud, select your repository and branch,
and set the main file path to **`app/streamlit_app.py`**. Choose **Python 3.13**
in Advanced settings to match the tested environment. Keep the supplied pins:
Streamlit 1.63.0, pandas 3.0.2 and Altair 6.2.2. The dependencies require Python
3.11 or newer.

Streamlit runs from the repository root and needs your dependency declarations
and local data files included. See the official
[file organisation guide](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/file-organization),
[dependency guide](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies),
and [deployment instructions](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy).

Do not deploy just an SVG or refer to your computer's Downloads folder. V2
builds the SVG on the deployed server from current results. It requires no
Excel installation, Graphviz, image converter or extra flowsheet dependency.

## If you have separately edited V1

Merge these files with your own edits rather than replacing unrelated changes:

- `app/streamlit_app.py`
- `openga_v1/engine.py`, `openga_v1/config.py` and `openga_v1/validation.py`
- `openga_v1/streams.py` and `openga_v1/stream_metadata.json` (new)
- `openga_flowsheet/` (new)
- `selftest.py`, `tests/` and the V2 documentation

The `openga_v1` backend name is retained for compatibility. The MEB, energy,
equipment and financial equations are unchanged.
