(() => {
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
