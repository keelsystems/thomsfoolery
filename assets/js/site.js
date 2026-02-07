async function loadJSON(path){
  const res = await fetch(path, { cache: "no-store" });
  if(!res.ok) throw new Error(`Failed to load ${path}`);
  return await res.json();
}

function fmtWhen(iso){
  try{
    const d = new Date(iso);
    return new Intl.DateTimeFormat(undefined, {
      weekday: "short",
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
      timeZone: "America/St_Johns",
      timeZoneName: "short"
    }).format(d);
  }catch{
    return iso;
  }
}

function byId(id){ return document.getElementById(id); }

async function hydrateHome(){
  const nextEl = byId("nextBlock");
  const latestEl = byId("latestGrid");
  if(!nextEl && !latestEl) return;

  const [schedule, latest] = await Promise.all([
    loadJSON("/content/schedule.json").catch(() => null),
    loadJSON("/content/latest.json").catch(() => null)
  ]);

  if(nextEl && schedule && Array.isArray(schedule.items)){
    const upcoming = schedule.items
      .filter(x => x && x.when)
      .sort((a,b) => new Date(a.when) - new Date(b.when))[0];

    if(upcoming){
      nextEl.innerHTML = `
        <div class="card">
          <div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:center">
            <div>
              <div class="tag gold">Up next</div>
              <h3 style="margin:10px 0 4px 0">${upcoming.title || "Next stream"}</h3>
              <div class="meta">${fmtWhen(upcoming.when)}${upcoming.where ? " · " + upcoming.where : ""}</div>
              <p style="margin-top:10px">${upcoming.note || ""}</p>
            </div>
            <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center">
              <a class="btn" href="/watch-parties.html">See schedule</a>
              <a class="btn primary" href="/links.html">Follow + notifications</a>
            </div>
          </div>
        </div>
      `;
    }
  }

  if(latestEl && latest && Array.isArray(latest.cards)){
    latestEl.innerHTML = latest.cards.slice(0,3).map(card => `
      <article class="card">
        <h3>${card.title || "Latest"}</h3>
        <p>${card.blurb || ""}</p>
        <div class="meta"><a href="${card.href || "#"}">${card.linkText || "Open"} →</a></div>
      </article>
    `).join("");
  }
}

async function hydrateSchedule(){
  const listEl = byId("scheduleList");
  if(!listEl) return;

  const schedule = await loadJSON("/content/schedule.json").catch(() => null);
  if(!schedule || !Array.isArray(schedule.items)) return;

  const items = schedule.items
    .filter(x => x && x.when)
    .sort((a,b) => new Date(a.when) - new Date(b.when))
    .slice(0, 20);

  listEl.innerHTML = items.map(x => `
    <div class="listItem">
      <div>
        <strong>${x.title || "Stream"}</strong>
        <div class="meta">${fmtWhen(x.when)}${x.where ? " · " + x.where : ""}</div>
        ${x.note ? `<div class="meta">${x.note}</div>` : ""}
      </div>
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        ${x.type ? `<span class="tag">${x.type}</span>` : ""}
        <a class="btn" href="/links.html">Links</a>
      </div>
    </div>
  `).join("");
}

(async function init(){
  try{
    await hydrateHome();
    await hydrateSchedule();
  }catch(e){
    console.warn(e);
  }
})();
