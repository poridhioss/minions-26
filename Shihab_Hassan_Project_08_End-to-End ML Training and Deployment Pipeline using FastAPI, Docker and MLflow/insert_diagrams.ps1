$file = "e:\Poridhi Intern\Push\minions-26\Shihab_Hassan_Project_08_End-to-End ML Training and Deployment Pipeline using FastAPI, Docker and MLflow\mlops-pipeline\README.md"
$content = Get-Content $file -Raw

# --- Diagram 2: Lifecycle of a single prediction (Chapter 4: prediction endpoint) ---
$lifeOld = "### Run the API`r`n`r`nFrom the project root:`r`n`r`n```powershell`r`nuvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`r`n```"
$lifeNew = "### Lifecycle of a Single Prediction`r`n`r`n![Lifecycle of a Single Prediction](`"Diagram And Picture/lifecycleofsinglepred.svg`")`r`n`r`nThis lifecycle view traces one customer record from the Streamlit UI all the way to the JSON you see in the browser. Each arrow is a real code path:`r`n`r`n1. **UI form** collects inputs and validates them client-side.`r`n2. **HTTP POST** hits FastAPI, which runs Pydantic validation on `PredictRequest` and `CustomerFeatures`.`r`n3. **ChurnPredictor** loads the persisted sklearn `Pipeline` once and reuses it for every call.`r`n4. **Preprocessor** (inside the pipeline) applies the exact scaling fit during training.`r`n5. **Model** returns a class (`0` / `1`) and a probability (`predict_proba`).`r`n6. **Response** is rendered as a green/red banner plus a progress bar in the UI.`r`n`r`n### Run the API`r`n`r`nFrom the project root:`r`n`r`n```powershell`r`nuvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`r`n```"

if ($content -notmatch 'Lifecycle of a Single Prediction') {
    if ($content.Contains("### Run the API`r`n`r`nFrom the project root:`r`n`r`n```powershell`r`nuvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`r`n```")) {
        $content = $content.Replace("### Run the API`r`n`r`nFrom the project root:`r`n`r`n```powershell`r`nuvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`r`n```", $lifeNew)
        Write-Host "Diagram 2 inserted"
    } else {
        Write-Host "ERROR: Diagram 2 anchor not found"
    }
} else {
    Write-Host "Diagram 2 already present - skipping"
}

# --- Diagram 3: System layers (Chapter 6: Containerization) ---
$sysOld = "### What you will build`r`n`r`nA single `Dockerfile` that runs an end-to-end bootstrap on first startup (generate â†’ preprocess â†’ train â†’ serve) so the image works on a fresh machine with zero pre-baked data."
$sysNew = "### What you will build`r`n`r`nA single `Dockerfile` that runs an end-to-end bootstrap on first startup (generate â†’ preprocess â†’ train â†’ serve) so the image works on a fresh machine with zero pre-baked data.`r`n`r`n### System Layers`r`n`r`n![System Layers](`"Diagram And Picture/systemlayers.svg`")`r`n`r`nBefore diving into the `Dockerfile`, it helps to see the whole system as a stack of layers. The image below summarizes them and the responsibilities of each:`r`n`r`n- **Client layer** — Browser, cURL, or any HTTP client that talks JSON to the API.`r`n- **Edge layer** — FastAPI app, Pydantic schemas, middleware (CORS, logging).`r`n- **Application layer** — `ChurnPredictor` wrapping the trained scikit-learn `Pipeline`.`r`n- **Model layer** — `models/best_model.joblib` + `models/preprocessor.joblib` on disk.`r`n- **Data layer** — `data/customer_churn.csv` and the `mlruns/` tracking store.`r`n- **Infrastructure layer** — Docker container, Python runtime, system libs."

if ($content -notmatch '### System Layers') {
    if ($content.Contains($sysOld)) {
        $content = $content.Replace($sysOld, $sysNew)
        Write-Host "Diagram 3 inserted"
    } else {
        Write-Host "ERROR: Diagram 3 anchor not found"
    }
} else {
    Write-Host "Diagram 3 already present - skipping"
}

Set-Content -Path $file -Value $content -NoNewline
Write-Host "All done."
