(() => {
  document.querySelectorAll(".directory-shot").forEach((shot) => {
    const backdrop = shot.querySelector("img").cloneNode();
    backdrop.className = "screenshot-backdrop";
    backdrop.alt = "";
    backdrop.setAttribute("aria-hidden", "true");
    shot.prepend(backdrop);
  });

  document.querySelectorAll(".disclosure-toggle").forEach((button) => {
    const disclosure = button.closest(".ai-disclosure");
    const panel = document.getElementById(button.getAttribute("aria-controls"));
    button.addEventListener("click", () => {
      const expanded = button.getAttribute("aria-expanded") !== "true";
      button.setAttribute("aria-expanded", String(expanded));
      panel.setAttribute("aria-hidden", String(!expanded));
      panel.inert = !expanded;
      disclosure.classList.toggle("is-open", expanded);
    });
  });

  const root = document.body.dataset.root || ".";
  const pluginId = document.body.dataset.plugin;
  const downloads = document.querySelector("[data-downloads]");
  const countSlots = document.querySelectorAll("[data-download-count]");

  if ((!pluginId || !downloads) && !countSlots.length) return;

  const formatBytes = (bytes) => {
    const megabytes = bytes / (1024 * 1024);
    return `${megabytes < 10 ? megabytes.toFixed(1) : Math.round(megabytes)} MB`;
  };

  const element = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  };

  const fileLabel = (file) => {
    if (file.name.endsWith(".exe") || file.name.endsWith(".pkg")) return "Installer";
    return "Portable ZIP";
  };

  const renderPlatform = (platformName, platform, files) => {
    const card = element("section", "platform-card");
    const heading = element("div", "platform-heading");
    heading.append(element("span", `os-mark ${platform}`), element("h4", "", platformName));
    card.append(heading);

    const details = platform === "win64"
      ? "Windows 10/11 · x64 · VST3"
      : "macOS 11+ · Apple silicon + Intel · AU + VST3";
    card.append(element("p", "platform-details", details));

    const links = element("div", "download-links");
    files.forEach((file) => {
      const link = element("a", "download-button");
      link.href = file.url;
      link.innerHTML = `<span>${fileLabel(file)}</span><small>${formatBytes(file.size)}</small>`;
      links.append(link);
    });
    card.append(links);
    return card;
  };

  fetch(`${root}/downloads.json`, { cache: "no-store" })
    .then((response) => {
      if (!response.ok) throw new Error("Download catalog could not be loaded.");
      return response.json();
    })
    .then((catalog) => {
      countSlots.forEach((slot) => {
        const countedPlugin = catalog.plugins[slot.dataset.downloadCount];
        if (!countedPlugin || !Number.isInteger(countedPlugin.downloads)) return;
        const latest = countedPlugin.versions[0];
        const releaseSlot = slot.parentElement.querySelector("[data-release-info]");
        if (latest && releaseSlot) {
          const parts = latest.version.match(/^(\d+(?:\.\d+)*)(.*)$/);
          const components = parts ? parts[1].split(".") : [];
          while (components.length && components.length < 3) components.push("0");
          const displayVersion = parts ? components.join(".") + parts[2] : latest.version;
          const date = latest.publishedAt && new Date(latest.publishedAt);
          const formattedDate = date && !Number.isNaN(date.getTime())
            ? new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }).format(date)
            : "";
          releaseSlot.textContent = `v${displayVersion}${formattedDate ? ` · ${formattedDate}` : ""}`;
        }
        slot.textContent = countedPlugin.downloads.toLocaleString();
        slot.setAttribute("aria-label", `${countedPlugin.downloads.toLocaleString()} downloads`);
      });

      if (!pluginId || !downloads) return;
      const plugin = catalog.plugins[pluginId];
      if (!plugin || !plugin.versions.length) throw new Error("No downloads are available yet.");

      downloads.replaceChildren();
      const latest = document.querySelector("[data-latest-version]");
      if (latest) latest.textContent = `Latest ${plugin.versions[0].version}`;

      plugin.versions.forEach((release, index) => {
        const version = element("article", "version-block");
        const header = element("header", "version-heading");
        const label = element("div");
        label.append(element("span", "version-kicker", index === 0 ? "CURRENT RELEASE" : "PREVIOUS RELEASE"));
        label.append(element("h3", "", `Version ${release.version}`));
        header.append(label);

        if (release.checksums && release.checksums.url) {
          const checksum = element("a", "checksum-link", "SHA-256 checksums");
          checksum.href = release.checksums.url;
          header.append(checksum);
        }

        version.append(header);
        const platforms = element("div", "platform-grid");
        platforms.append(
          renderPlatform("Windows", "win64", release.platforms.win64 || []),
          renderPlatform("macOS", "macos", release.platforms.macos || [])
        );
        version.append(platforms);
        downloads.append(version);
      });
    })
    .catch((error) => {
      if (downloads) downloads.replaceChildren(element("p", "download-error", error.message));
    });
})();
