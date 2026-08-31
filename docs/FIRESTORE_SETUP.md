# Firestore setup — a Google Cloud service with no billing account

## Why this path exists

The hackathon rules require **at least one Google Cloud infrastructure
service**, naming Cloud Run, Cloud SQL, Firestore, GKE and Pub/Sub.

Cloud Run requires a billing account. **Firestore does not** — the Firebase
Spark plan includes Cloud Firestore free, with no card and no billing account,
and a Firebase project *is* a Google Cloud project. So when Cloud Run is
unavailable, Firestore satisfies requirement 3 on its own terms.

**State the limitation honestly in your submission.** The rules also ask the
video to "demonstrate the backend is running on Google Cloud". Firestore is a
genuine Google Cloud service holding your live application data, but it does
not host the backend. Show the Firestore console with real documents in it and
say exactly what it is. Do not imply a Cloud Run deployment that does not
exist — a judge who checks will find out, and the honesty is worth more than
the claim.

## Setup

**1.** Create a project at <https://console.firebase.google.com> — Spark plan,
no card requested.

**2.** In the console, open **Build → Firestore Database → Create database**.
Pick a location near you (`asia-southeast1` for Malaysia). Start in
**production mode**; this app writes with a service account, not from a
browser, so open security rules are unnecessary.

**3.** Get credentials. In **Project settings → Service accounts → Generate new
private key**, download the JSON, and keep it out of the repo — `.gitignore`
already excludes `*.json` credentials by pattern, but check before committing.

**4.** Point the app at it:

```bash
export GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/serviceAccount.json
export NADI_USE_FIRESTORE=true
export NADI_FIRESTORE_PROJECT=your-firebase-project-id
```

On Windows PowerShell:

```powershell
$env:GOOGLE_APPLICATION_CREDENTIALS="C:\path\to\serviceAccount.json"
$env:NADI_USE_FIRESTORE="true"
$env:NADI_FIRESTORE_PROJECT="your-firebase-project-id"
```

**5.** Start the server. On first run it seeds the Aurora / Jalur Kita demo
corpus into Firestore automatically:

```bash
uvicorn nadi.api.app:app --port 8080
```

Watch the log line. `Store backend: Firestore (project=...)` means it
connected. `Firestore unavailable, falling back to in-memory store: ...`
means it did not, and the message says why — the service still boots either
way, because failing a demo is worse than losing persistence.

## Verify it is actually persisting

Draft a holding statement in the console, then **stop and restart the server**.
If the draft is still there, it came out of Firestore rather than memory. You
can also watch the documents appear live in the Firebase console under
`nadi_holdings`, which is the shot to use in the demo video.

## What it stores

| Collection | Contents |
|------------|----------|
| `nadi_mentions` | Ingested mentions with 3R flags |
| `nadi_snapshots` | Locked AMEC evaluation snapshots |
| `nadi_war_rooms` | Crisis war rooms |
| `nadi_holdings` | Holding statement drafts |

Every document carries `org_id` and `workspace_id`, and every read is a
composite Firestore filter on both — a document belonging to another tenant is
never returned, rather than being filtered out in Python afterwards. Direct
lookup by a guessed document id is scope-checked too.

Models are **re-validated on read**, so the product invariants (`ave=False`,
`auto_publish=False`, `human_must_send=True`) are re-applied coming *out* of
the database. Editing a row by hand in the Firestore console cannot
reintroduce AVE or produce a holding that publishes itself — there is a test
that does exactly this and asserts the tampering is neutralised.

## Free tier limits

Spark gives 1 GiB storage, 50k document reads and 20k writes per day. This
demo's entire corpus is four documents, so judging traffic will not come close.

## Cost note

The Spark plan cannot incur charges — there is no billing account attached to
exceed. If you later upgrade to Blaze, set a budget alert first.
