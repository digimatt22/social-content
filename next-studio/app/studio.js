"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const hosted = process.env.NEXT_PUBLIC_STUDIO_HOSTED === "1";
const api = `${hosted ? "/studio" : ""}/api/studio`;
const librarySection = hosted ? "Products" : "Photo library";
const sections = ["Posts", librarySection];
const postStages = ["Draft", "Review"];
const gateNames = ["Idea and relevance", "Visual execution", "Product and factual truth", "Copy and outcome"];
const date = (time) => new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZone: "America/New_York" }).format(time);
const version = (id) => id.slice(0, 8);
const photoUrl = (photo) => photo.preview ?? `${api}/source/${photo.id}${photo.sha256 ? `?hash=${photo.sha256}` : ""}`;
const empty = { assignments: [], copy: [], jobs: [], proposals: [], artifacts: [], reviews: [] };

function ImageStrip({ photos }) {
  return <div className="image-strip">{photos.map(photo =>
    <a key={photo.id} href={photoUrl(photo)} target="_blank" rel="noreferrer">
      <img src={photoUrl(photo)} alt={photo.product} />
      <span>{photo.file}</span>
    </a>)}</div>;
}

function Library({ catalog, selected, toggle }) {
  return <div className="library">{catalog.map(photo => <div className="photo" key={photo.id}>
    <img src={photoUrl(photo)} alt={photo.product} loading="lazy" referrerPolicy="no-referrer" />
    <div><strong>{photo.product}</strong><small>{photo.file}</small>
      {photo.kind && <small>{photo.kind === "etsy" ? "Etsy reference" : "Uploaded original"}</small>}
      {toggle && <button type="button" className="quiet" aria-pressed={selected.includes(photo.id)}
        disabled={selected.length >= 4 && !selected.includes(photo.id)}
        onClick={() => toggle(photo.id)}>{selected.includes(photo.id) ? `Reference ${selected.indexOf(photo.id) + 1}` : "Select photo"}</button>}
    </div>
  </div>)}</div>;
}

function ProductBrowser({ selected, toggle, submit, busy, initialProductId = "", startPost }) {
  const [products, setProducts] = useState([]);
  const [id, setId] = useState(initialProductId);
  const [search, setSearch] = useState("");
  const [photos, setPhotos] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(Boolean(initialProductId));

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${api}/products`, { signal: controller.signal }).then(async response => {
      if (!response.ok) throw new Error("The catalog could not load.");
      setProducts((await response.json()).products);
    }).catch(failure => { if (failure.name !== "AbortError") setError(failure.message); });
    return () => controller.abort();
  }, []);

  const refreshPhotos = useCallback(async (productId, signal) => {
    try {
      const response = await fetch(`${api}/product-photos/${productId}`, { signal });
      if (!response.ok) throw new Error("Product photos could not load.");
      const result = await response.json();
      if (!signal?.aborted) setPhotos(result.photos);
    } catch (failure) {
      if (!signal?.aborted) setError(failure.message);
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!id) return;
    const controller = new AbortController();
    refreshPhotos(id, controller.signal);
    return () => controller.abort();
  }, [id, refreshPhotos]);

  const visible = products.filter(product => String(product.id) === id ||
    product.name.toLowerCase().includes(search.trim().toLowerCase()));
  return <div>
    <div className="grid two">
      <label>Search products <input type="search" value={search} onChange={e => setSearch(e.target.value)} /></label>
      <label>Product <select value={id} onChange={e => {
        setPhotos([]);
        setError("");
        setLoading(Boolean(e.target.value));
        setId(e.target.value);
      }}>
        <option value="">Choose a product</option>
        {visible.map(product => <option key={product.id} value={product.id}>{product.name}</option>)}
      </select></label>
    </div>
    {error && <p role="alert" className="error">{error}</p>}
    {loading && <p className="muted" role="status">Loading photos…</p>}
    {search.trim() && !visible.length && <p className="muted" role="status">No matching products.</p>}
    {id && !loading && !photos.length && !error && <p className="muted">This product has no available photos.</p>}
    {!toggle && id && photos.length > 0 && <button className="product-post" type="button" onClick={() => startPost(id)}>Start a post with this product</button>}
    <Library catalog={photos} selected={selected} toggle={toggle} />
    {id && !toggle && <form onSubmit={async e => {
      e.preventDefault();
      const form = e.currentTarget;
      if (await submit(`upload-source/${id}`, new FormData(form))) {
        form.reset();
        await refreshPhotos(id);
      }
    }}>
      <label>Upload an original photo <input type="file" name="image" accept="image/png,image/jpeg,image/webp" required /></label>
      <button type="submit" disabled={busy}>Attach to product</button>
    </form>}
  </div>;
}

function NewAssignment({ catalog, create, busy, cancel, productId }) {
  const [selected, setSelected] = useState([]);
  const heading = useRef(null);
  useEffect(() => { heading.current?.focus(); }, []);
  const toggle = (id) => setSelected(prev => prev.includes(id) ? prev.filter(item => item !== id) : prev.length < 4 ? [...prev, id] : prev);
  return <form className="card new-assignment" onSubmit={(e) => {
    e.preventDefault();
    create({ ...Object.fromEntries(new FormData(e.currentTarget)), sourceIds: selected });
  }}>
    <div className="row"><h2 ref={heading} tabIndex={-1}>New post</h2><button className="quiet" type="button" onClick={cancel}>Cancel</button></div>
    <fieldset>
      <legend>Post idea</legend>
      <label>Working title <input name="title" required maxLength={100} placeholder="A recognizable moment for this duck" /></label>
      <div className="grid two">
        <label>Who is this for? <textarea name="audience" required placeholder="Who recognizes this moment?" /></label>
        <label>What will they see or discover? <textarea name="payoff" required /></label>
      </div>
    </fieldset>
    <fieldset>
      <legend>Reference photos</legend>
      <p className="muted" role="status">Select 1 to 4 photos in the order you want to use them. {selected.length} selected.</p>
      {hosted ? <ProductBrowser selected={selected} toggle={toggle} initialProductId={productId} /> : <Library catalog={catalog} selected={selected} toggle={toggle} />}
    </fieldset>
    <fieldset>
      <legend>Post details</legend>
      <div className="grid three">
        <label>Outcome <select name="outcome"><option>Follower growth</option><option>Engagement</option><option>Drive sales</option></select></label>
        <label>Channel <select name="channel"><option>Instagram</option><option>Facebook</option><option>Pinterest</option><option>X</option><option>r/3dprintedducks</option></select></label>
        <label>Format <select name="format"><option>Still image</option><option>Photo carousel</option></select></label>
      </div>
      <div className="grid two">
        <label>Which detail makes this product fit? <textarea name="fit" required /></label>
        <label>What should viewers do next? <textarea name="action" required /></label>
      </div>
      <label>How will you judge the result? <textarea name="measure" required placeholder="Metric, when you will check it, and what would justify another post" /></label>
    </fieldset>
    <button disabled={busy || !selected.length}>Create post</button>
  </form>;
}

function Magnific({ brief, proposals, artifacts, action, attach, busy }) {
  const [chosen, choose] = useState(null);
  const proposal = proposals.find(item => item.started) ?? proposals.find(item => item.id === chosen) ?? proposals[0];
  const completed = artifacts.find(asset => asset.proposal_id === proposal?.id);
  const started = proposals.some(item => item.started);
  const [newProposal, setNewProposal] = useState(false);
  const settings = proposal?.settings;
  const payload = (command, extra = {}) => action({ command, proposalId: proposal.id, ...extra });
  return <section className="card">
    <div className="row"><div><span className="eyebrow">Magnific</span><h2>Image production</h2></div>{proposal && !started &&
      <button type="button" className="quiet" onClick={() => setNewProposal(!newProposal)}>{newProposal ? "Close" : "New proposal"}</button>}</div>
    {(!proposal || newProposal) && <form onSubmit={async (e) => {
      e.preventDefault();
      if (await action({ command: "propose-image", ...Object.fromEntries(new FormData(e.currentTarget)) })) {
        choose(null);
        setNewProposal(false);
      }
    }}>
      <label>Scene and composition <textarea name="scene" required maxLength={1700} placeholder="Name the subjects, how they are arranged, and what must stay visible." /></label>
      <div className="row"><label>Aspect ratio <select name="ratio" defaultValue="4:5"><option>4:5</option><option>1:1</option><option>9:16</option><option>2:3</option></select></label>
        <button disabled={busy}>Save image proposal</button></div>
    </form>}
    {proposal && <div className="proposal" key={proposal.id}>
      {proposals.length > 1 && !started && <label>Proposal <select value={proposal.id} onChange={e => choose(e.target.value)}>{proposals.map(p =>
        <option key={p.id} value={p.id}>{version(p.id)} · {p.settings.aspectRatio}</option>)}</select></label>}
      <h3>Nano Banana Pro Flash · {settings.aspectRatio} · {settings.resolution}</h3>
      <p className="muted">One image. Full scene from original references. No retries.</p>
      <ImageStrip photos={brief.sources} />
      <details><summary>Exact prompt and reference order</summary><p className="prompt">{settings.prompt}</p></details>
      <a className="download" download={`magnific-${version(proposal.id)}.json`}
        href={`data:application/json;charset=utf-8,${encodeURIComponent(JSON.stringify({ proposalId: proposal.id, ...settings }, null, 2))}`}>Download proposal</a>
      {!proposal.approved && <form onSubmit={(e) => {
        e.preventDefault();
        const fields = new FormData(e.currentTarget);
        payload("record-quote", { credits: Number(fields.get("credits")), receipt: fields.get("receipt") });
      }}>
        <p className="muted">Run Magnific’s cost simulation for these settings and record its estimate.</p>
        <div className="grid quote-fields">
          <label>Estimated credits <input type="number" min="1" name="credits" key={proposal.quote?.recorded} defaultValue={proposal.quote?.credits} required /></label>
          <label>Simulation receipt <input name="receipt" key={proposal.quote?.receipt} defaultValue={proposal.quote?.receipt} required placeholder="Quote reference or simulation response" /></label>
        </div>
        <button className="quiet" disabled={busy}>Save quote</button>
      </form>}
      {proposal.quote && !proposal.approved && <div className="decision-bar"><span>{proposal.quote.credits} credits maximum</span>
        <button type="button" disabled={busy} onClick={() => payload("approve-image", { credits: proposal.quote.credits })}>Approve this proposal</button></div>}
      {proposal.approved && <p className="state-line">Approved · {proposal.quote.credits} credits maximum · {date(proposal.approved)}</p>}
      {proposal.approved && !proposal.started && <div className="decision-bar"><span>Generate in Magnific with this proposal and the original photos.</span>
        <button type="button" disabled={busy} onClick={() => payload("start-image", { credits: proposal.quote.credits })}>Start Magnific handoff</button></div>}
      {proposal.started && !completed && <form onSubmit={async (e) => {
        e.preventDefault();
        const form = new FormData(e.currentTarget);
        form.set("proposalId", proposal.id);
        await attach(form);
      }}>
        <h3>Attach the completed image</h3>
        <label>Magnific task or creation ID <input name="providerId" required maxLength={160} /></label>
        <label>Output image <input name="image" type="file" accept="image/png,image/jpeg,image/webp" required /></label>
        <button disabled={busy}>Attach result</button>
      </form>}
      {completed && <p className="state-line">Image attached · {completed.provider_id}</p>}
    </div>}
  </section>;
}

function Draft({ assignment, records, action, attach, busy, copyAvailable }) {
  const brief = assignment.brief;
  const job = records.jobs[0];
  const active = job && ["queued", "submitting", "running", "uncertain"].includes(job.state);
  return <>
    <section className="card">
      <h3>Post brief</h3>
      <dl className="brief grid two">
        <div><dt>Audience situation</dt><dd>{brief.audience}</dd></div>
        <div><dt>Visible payoff</dt><dd>{brief.payoff}</dd></div>
        <div><dt>Source detail</dt><dd>{brief.fit}</dd></div>
        <div><dt>Viewer action</dt><dd>{brief.action}</dd></div>
      </dl>
      <h3>Reference photos · {brief.format}</h3>
      <ImageStrip photos={brief.sources} />
    </section>
    <section className="card" id="copy">
      <div className="row"><h3>Caption</h3>
        {copyAvailable && <button className="quiet" disabled={busy || active} onClick={() => action({ command: "queue-copy" })}>Draft with OpenAI</button>}</div>
      {job && <p className="state-line" role="status">OpenAI · {job.state}{job.detail ? ` · ${job.detail}` : ""}</p>}
      <form key={records.copy[0]?.id ?? "empty"} onSubmit={(e) => {
        e.preventDefault();
        action({ command: "save-copy", caption: new FormData(e.currentTarget).get("caption") });
      }}>
        <label>Caption <textarea name="caption" required maxLength={2200} defaultValue={records.copy[0]?.caption} rows={4} /></label>
        <button disabled={busy}>{records.copy.length ? "Save caption version" : "Save caption"}</button>
      </form>
      {records.copy.length > 0 && <details><summary>{records.copy.length} saved {records.copy.length === 1 ? "version" : "versions"}</summary>
        {records.copy.map(item => <article key={item.id} className="version"><strong>{version(item.id)} · {item.origin === "openai" ? "OpenAI" : "Manual"}</strong><p>{item.caption}</p></article>)}
      </details>}
    </section>
    {brief.format === "Still image" && <details className="image-tools" open={records.proposals.length > 0}>
      <summary>Generate an image with Magnific</summary>
      <Magnific brief={brief} proposals={records.proposals} artifacts={records.artifacts} action={action} attach={attach} busy={busy} />
    </details>}
  </>;
}

function Review({ records, action, busy, openDraft }) {
  const [mediaId, setMedia] = useState("");
  const [copyId, setCopy] = useState("");
  const asset = records.artifacts.find(item => item.id === mediaId) ?? records.artifacts[0];
  const copy = records.copy.find(item => item.id === copyId) ?? records.copy[0];

  if (!asset || !copy) return <section className="card">
    <h3>{copy ? "Add media before review" : "Save a caption before review"}</h3>
    <p>{copy ? "Add the image you want to review in Draft." : "Save a caption in Draft, then review it alongside its image."}</p>
    <button type="button" onClick={openDraft}>Back to draft</button>
  </section>;

  return <>
    <section className="card">
      <h3>Review a version</h3>
      <div className="grid two">
        <label>Media <select value={asset.id} onChange={e => setMedia(e.target.value)}>{records.artifacts.map(item =>
          <option key={item.id} value={item.id}>{item.flags.kind === "originals" ? "Original photos" : "Magnific image"} · {version(item.id)}</option>)}</select></label>
        <label>Caption <select value={copy.id} onChange={e => setCopy(e.target.value)}>{records.copy.map(item =>
          <option key={item.id} value={item.id}>{item.origin} · {version(item.id)}</option>)}</select></label>
      </div>
      <div className="review-preview">
        {asset.flags.kind === "magnific" ? <img className="review-image" src={`${api}/artifact/${asset.id}`} alt="Magnific candidate at feed size" /> : <ImageStrip photos={asset.flags.sources} />}
        <blockquote>{copy.caption}</blockquote>
      </div>
      {asset.flags.kind === "magnific" && <details><summary>Compare with original photos</summary><ImageStrip photos={asset.flags.sources} /></details>}
      <form key={asset.id + copy.id} onSubmit={async (e) => {
        e.preventDefault();
        const form = e.currentTarget;
        const fields = new FormData(form);
        if (await action({ command: "review", copyId: copy.id, artifactId: asset.id,
          verdicts: fields.getAll("verdict"), evidence: fields.getAll("evidence") })) form.reset();
      }}>
        {gateNames.map(name => <div className="review-gate" key={name}>
          <label>{name}<select name="verdict" defaultValue="" required><option value="" disabled>Choose verdict</option>
            <option>Pass</option><option>Revise</option><option>Reject</option><option>Blocked</option></select></label>
          <label>Evidence <input required name="evidence" maxLength={500} aria-label={`${name} evidence`} /></label>
        </div>)}
        <button disabled={busy}>Save review</button>
      </form>
    </section>
    {records.reviews.map(review => <section className="card" key={review.id}>
      <h3>Review · {date(review.created)}</h3>
      <p className="muted">Media {version(review.artifact_id)} · Copy {version(review.copy_id)}</p>
      <dl>{review.judgment.map(gate => <div key={gate.name}><dt>{gate.name} · {gate.verdict}</dt><dd>{gate.evidence}</dd></div>)}</dl>
      {review.owner_decision ? <p className="state-line">{review.owner_decision} · {review.owner_note}</p> :
        <form onSubmit={e => {
          e.preventDefault();
          action({ command: "owner-decision", reviewId: review.id, ...Object.fromEntries(new FormData(e.currentTarget)) });
        }}>
          <div className="grid two"><label>Owner decision <select name="decision">
            <option>Request revision</option><option>Defer</option>
            {review.judgment.every(gate => gate.verdict === "Pass") && <option>Accept creative</option>}
          </select></label><label>Decision note <input name="note" required maxLength={500} /></label></div>
          <button disabled={busy}>Record decision</button>
        </form>}
    </section>)}
  </>;
}

export default function Studio({ catalog }) {
  const [data, setData] = useState(empty);
  const [section, setSection] = useState("Posts");
  const [stage, setStage] = useState("Draft");
  const [id, setId] = useState("");
  const [newPost, setNewPost] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const csrf = useRef("");
  const refresh = useCallback(async () => {
    const response = await fetch(`${api}/state`, { cache: "no-store" });
    if (hosted && response.status === 401) { window.location.assign("/auth/login"); return; }
    if (!response.ok) throw new Error("The studio could not load.");
    csrf.current = response.headers.get("X-CSRF-Token") ?? "";
    setData(await response.json());
    setLoading(false);
  }, []);

  useEffect(() => {
    refresh().catch(error => { setError(error.message); setLoading(false); });
    const timer = setInterval(() => { if (!document.hidden) refresh().catch(() => {}); }, 4000);
    return () => clearInterval(timer);
  }, [refresh]);

  async function submit(path, body) {
    setBusy(true);
    setError("");
    try {
      const form = body instanceof FormData;
      const headers = new Headers(form ? undefined : { "Content-Type": "application/json" });
      if (hosted) {
        if (!csrf.current) throw new Error("Reload Studio to refresh your sign-in, then try again.");
        headers.set("X-CSRF-Token", csrf.current);
      }
      const response = await fetch(`${api}/${path}`, {
        method: "POST", headers,
        body: form ? body : JSON.stringify(body),
      });
      if (hosted && response.status === 401) { window.location.assign("/auth/login"); return null; }
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Your change could not be saved.");
      await refresh();
      return result;
    } catch (error) {
      setError(error.message);
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function signOut() {
    try {
      if (!csrf.current) throw new Error();
      const response = await fetch("/auth/logout", { method: "POST", headers: { "X-CSRF-Token": csrf.current } });
      if (!response.ok) throw new Error();
      window.location.assign("/auth/login");
    } catch {
      setError("Sign-out could not be completed. Reload the page and try again.");
    }
  }

  const assignment = data.assignments.find(item => item.id === id) ?? data.assignments[0];
  const records = Object.fromEntries(["copy", "jobs", "proposals", "artifacts", "reviews"].map(key => [
    key, data[key].filter(item => item.assignment_id === assignment?.id),
  ]));
  const action = (body) => submit(`command/${assignment.id}`, body);
  const go = (next) => {
    if (next === section) return;
    setSection(next);
    setNewPost(null);
    setError("");
  };
  const startPost = (productId = "") => {
    setSection("Posts");
    setStage("Draft");
    setNewPost({ productId });
    setError("");
  };
  const currentReview = records.reviews.find(item =>
    item.copy_id === records.copy[0]?.id && item.artifact_id === records.artifacts[0]?.id);
  const postStatus = !records.copy.length ? "Needs a caption" : !records.artifacts.length ? "Needs media" :
    currentReview?.owner_decision ?? (currentReview ? "Awaiting decision" : "Ready for review");

  return <>
    <header><div className="header-inner">
      <a className="brand" href="/"><span className="mark" aria-hidden="true">M</span><span>MattMadeMe<small>Social Studio</small></span></a>
      <nav aria-label="Studio">{sections.map(name => <button key={name} type="button" className={section === name ? "active" : ""}
        aria-current={section === name ? "page" : undefined} onClick={() => go(name)}>{name}</button>)}</nav>
      {hosted && <div className="studio-account">
        <a href="/legacy">Older dashboard</a>
        <button type="button" onClick={signOut}>Sign out</button>
      </div>}
    </div></header>
    <main>
      <div className="page-title"><h1>{section}</h1>
        {section === "Posts" && !newPost && assignment && <button type="button" onClick={() => startPost()}>New post</button>}
      </div>
      {error && <div className="error" role="alert">{error}</div>}
      {section === librarySection && <section className="card">
        {hosted ? <><div className="row"><h2>Product catalog</h2><a href="/products">Edit product details</a></div><ProductBrowser submit={submit} busy={busy} startPost={startPost} /></> : <><h2>Original photos</h2><Library catalog={catalog} /></>}
      </section>}
      {section === "Posts" && newPost && <NewAssignment catalog={catalog} productId={newPost.productId} busy={busy} cancel={() => setNewPost(null)} create={async body => {
        const result = await submit("assignment", body);
        if (result) { setId(result.id); setNewPost(null); }
      }} />}
      {section === "Posts" && !newPost && assignment && <div className="workspace">
        <aside className="assignment-list" aria-label="Saved posts">
          {data.assignments.map(item => <button key={item.id} type="button" className={item.id === assignment.id ? "selected" : ""}
            aria-current={item.id === assignment.id ? "true" : undefined} onClick={() => {
              if (item.id !== assignment.id) { setId(item.id); setStage("Draft"); setError(""); }
            }}><strong>{item.brief.title}</strong><small>{item.brief.channel} · {item.brief.outcome}</small></button>)}
        </aside>
        <div className="stack" key={assignment.id}>
          <div className="post-heading">
            <p className="muted">{assignment.brief.channel} · {assignment.brief.outcome}</p>
            <h2>{assignment.brief.title}</h2>
            <div className="row">
              <div className="post-stages" role="group" aria-label="Post stages">
                {postStages.map(name => <button key={name} type="button" className="quiet" aria-pressed={stage === name} onClick={() => { setStage(name); setError(""); }}>{name}</button>)}
              </div>
              <span className="post-status">{postStatus}</span>
            </div>
          </div>
          <div hidden={stage !== "Draft"}>
            <div className="stack">
              <Draft assignment={assignment} records={records} action={action} busy={busy} copyAvailable={data.copyAvailable} attach={form => submit(`attach/${assignment.id}`, form)} />
              {records.copy.length > 0 && records.artifacts.length > 0 && <div><button type="button" onClick={() => { setStage("Review"); setError(""); }}>Review post</button></div>}
            </div>
          </div>
          <div hidden={stage !== "Review"}>
            <div className="stack">
              <Review records={records} action={action} busy={busy} openDraft={() => setStage("Draft")} />
              <section className="card"><h3>Measurement plan</h3><p>{assignment.brief.measure}</p></section>
            </div>
          </div>
        </div>
      </div>}
      {section === "Posts" && !newPost && !assignment &&
        <div className="empty">
          {loading ? <p role="status">Loading posts…</p> : <>
            <h2>Start a post</h2>
            <p>Choose reference photos, write a caption, and review them together.</p>
            <button type="button" onClick={() => startPost()}>New post</button>
          </>}
        </div>}
    </main>
  </>;
}
