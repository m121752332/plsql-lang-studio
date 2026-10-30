// 使用說明網頁：主題、章節跳轉、搜尋、目錄同步。說明程式透過 setTheme()／helpShow() 控制。
(function () {
  "use strict";
  const root = document.documentElement;

  // 使用者在說明視窗按過主題鈕後，再按 F1 開說明不會被蓋回主程式的主題；主程式換主題時才跟著換
  let manual = false;

  function applyTheme(theme) {
    root.dataset.theme = theme === "dark" ? "dark" : "light";
  }

  function setTheme(theme) {
    manual = false;
    applyTheme(theme);
  }

  function toggleTheme() {
    manual = true;
    applyTheme(root.dataset.theme === "dark" ? "light" : "dark");
  }

  function helpShow(topic, theme) {
    if (!manual) applyTheme(theme);
    const el = topic ? document.getElementById(topic) : null;
    history.replaceState(null, "", el ? "#" + topic : location.pathname + location.search);
    if (el) el.scrollIntoView(); else window.scrollTo(0, 0);
  }

  window.setTheme = setTheme;
  window.helpShow = helpShow;

  // 在 <head> 就套主題，開啟時不會先閃一下亮色
  const q = new URLSearchParams(location.search).get("theme");
  setTheme(q || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"));

  function clearMarks(main) {
    main.querySelectorAll("mark").forEach(function (m) {
      m.replaceWith(document.createTextNode(m.textContent));
    });
    main.normalize();
  }

  function markText(section, word) {
    const walker = document.createTreeWalker(section, NodeFilter.SHOW_TEXT);
    const hits = [];
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      if (n.nodeValue.toLowerCase().includes(word)) hits.push(n);
    }
    hits.forEach(function (node) {
      const text = node.nodeValue, lower = text.toLowerCase(), frag = document.createDocumentFragment();
      let i = 0, j;
      while ((j = lower.indexOf(word, i)) !== -1) {
        frag.append(text.slice(i, j));
        const m = document.createElement("mark");
        m.textContent = text.slice(j, j + word.length);
        frag.append(m);
        i = j + word.length;
      }
      frag.append(text.slice(i));
      node.replaceWith(frag);
    });
    // 常見問題收合著時，展開有命中的那一題
    section.querySelectorAll("details").forEach(function (d) {
      if (d.querySelector("mark")) d.open = true;
    });
  }

  function filter(main, links, word) {
    clearMarks(main);
    const hero = main.querySelector(".hero");
    if (hero) hero.hidden = !!word;
    let shown = 0;
    main.querySelectorAll("main > section").forEach(function (s) {
      const hit = !word || s.textContent.toLowerCase().includes(word);
      s.classList.toggle("hidden", !hit);
      const link = links[s.id];
      if (link) link.classList.toggle("hidden", !hit);
      if (hit) { shown++; if (word) markText(s, word); }
    });
    // 群組底下的章節都沒命中時，群組標題也藏起來
    document.querySelectorAll("#toc .group").forEach(function (g) {
      let any = false;
      for (let el = g.nextElementSibling; el && !el.classList.contains("group"); el = el.nextElementSibling) {
        if (el.tagName === "A" && !el.classList.contains("hidden")) any = true;
      }
      g.classList.toggle("hidden", !any);
    });
    document.getElementById("no-result").hidden = shown > 0;
  }

  document.addEventListener("DOMContentLoaded", function () {
    const main = document.querySelector("main");
    const links = {};
    document.querySelectorAll("#toc a[href^='#']").forEach(function (a) { links[a.hash.slice(1)] = a; });

    // 點截圖以原尺寸顯示，再點一下或按 Esc 關閉
    const zoom = document.createElement("div");
    zoom.id = "zoom";
    zoom.hidden = true;
    zoom.addEventListener("click", function () { zoom.hidden = true; });
    document.body.append(zoom);
    main.querySelectorAll("figure img").forEach(function (img) {
      img.addEventListener("click", function () {
        zoom.replaceChildren(img.cloneNode());
        zoom.hidden = false;
      });
    });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") zoom.hidden = true; });

    document.getElementById("theme-toggle").addEventListener("click", toggleTheme);

    const search = document.getElementById("search");
    search.addEventListener("input", function () { filter(main, links, search.value.trim().toLowerCase()); });

    // 捲動時標示目前章節
    const observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        Object.values(links).forEach(function (a) { a.classList.remove("active"); });
        const a = links[e.target.id];
        if (a) { a.classList.add("active"); a.scrollIntoView({ block: "nearest" }); }
      });
    }, { rootMargin: "0px 0px -70% 0px" });
    main.querySelectorAll("main > section").forEach(function (s) { observer.observe(s); });
  });
})();
