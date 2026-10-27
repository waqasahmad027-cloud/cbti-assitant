# CBTI Assistant (Vercel edition)

## 1. Objective

The CBTI Assistant answers questions on NSCSTI 2.0, SOPs and policy documents. Users open a domain link, enter a shared access code and ask in natural language; each answer is grounded in the approved documents and shown with its source passages. Questions the documents cannot answer are flagged. An administrator adds and removes documents from a password-protected page at `/admin`, without redeploying.

## 2. Document Overview

| Item | Detail |
|---|---|
| User page | `/` (access code) |
| Admin page | `/admin` (admin password): documents, upload, retrieval test, system check |
| Hosting | Vercel (free Hobby plan): static pages plus one Python function `api/index.py` |
| Storage | Supabase free project (Postgres with pgvector): documents, passages, vectors |
| Models | Hugging Face Inference Providers: `BAAI/bge-small-en-v1.5` (search), `Qwen/Qwen2.5-7B-Instruct` (answers) |
| Not stored | The original PDF/Word files. Only the extracted passages are kept. |

## 3. Setup

**3.1 Supabase.** Create a free project at supabase.com. Open SQL Editor, paste the whole of `supabase_schema.sql` and run it. Then open Project Settings, API, and note the Project URL and the `service_role` key. The `service_role` key is a secret: it goes only into Vercel's environment variables, never into a file or a message.

**3.2 Code on GitHub.** Create a **private** GitHub repository and upload the contents of this folder. No documents are in the folder; they are added later through `/admin`.

**3.3 Vercel.** At vercel.com choose Add New, Project, and import the repository. Leave the framework as "Other" and make no build settings. Before deploying, add these Environment Variables:

| Name | Value |
|---|---|
| `SUPABASE_URL` | Project URL from step 3.1 |
| `SUPABASE_SERVICE_KEY` | `service_role` key from step 3.1 |
| `HF_TOKEN` | Hugging Face fine-grained token with permission to make calls to Inference Providers |
| `ACCESS_CODE` | The shared code given to users |
| `ADMIN_PASSWORD` | A long password for `/admin` |
| `MIN_SCORE` | Optional; start with `0.5` and tune (section 5) |

Then deploy. The result is available at an address of the form `project-name.vercel.app`.

**3.4 Domain.** In the Vercel project, open Settings, Domains, add the domain and follow the DNS instructions shown there.

## 4. First Use

1. Open `/admin`, sign in, and press **Run check** under System check. The database, embeddings and answer model should each show `ok`. If one shows `FAILED`, the message states the cause (for example a wrong key or token).
2. Under Add a document, upload the guidebook and the SOPs one at a time. A progress bar shows the passages being indexed. If indexing is interrupted, press Resume against that file.
3. Open the user page, enter the access code and ask test questions.

To remove a document, press Delete in the list. To replace one, upload a file with the same name.

## 5. Choosing MIN_SCORE (the "not covered" control)

Under Test retrieval, type several questions that the documents answer and several that they do not, and note the best-match score of each. Set `MIN_SCORE` in Vercel (Settings, Environment Variables) between the two groups, then redeploy. Questions that name a metric (for example "Metric 6") are always answered from the repository, regardless of the score.

## 6. Roles and Responsibilities

| Activity | Administrator | Reader (user) |
|---|---|---|
| Hold admin password, Supabase and Hugging Face keys | R, A | – |
| Add, replace and delete documents | R, A | – |
| Verify answers against the displayed sources | C | R |
| Change the access code | R, A | I |

R = responsible, A = accountable, C = consulted, I = informed.

## 7. Limitations

- Each upload is limited to 4 MB, the request limit of Vercel functions. Larger files must be split.
- Scanned PDFs without a text layer cannot be read.
- Word files carry no page numbers; their citations show the section.
- The Vercel Hobby plan is for non-commercial use; the Supabase free plan pauses a project after a week without activity (it resumes from the Supabase dashboard).
- Every answer uses the allowance of the Hugging Face token. When it is exhausted, answers fail but the passages still display.
- The access code is shared, so it limits casual access but does not identify individual users.
- Changing the embedding model requires changing `vector(384)` in the schema and re-uploading all documents.

## 8. Local Testing (optional)

    pip install -r requirements.txt
    python tests/test_api.py                 # full test with test embeddings, no network
    python tests/test_supabase_requests.py   # checks the database calls
    python dev.py                            # local server at http://127.0.0.1:8000

`dev.py` uses a local JSON file instead of Supabase unless `SUPABASE_URL` is set.
