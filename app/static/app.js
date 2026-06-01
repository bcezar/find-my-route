// TODO: reorganize methods by category (state init, inputs, map, actions, utils)
function routeApp() {
  return {
    originInput: '', origin: '', originSuggestions: [],
    destInput:   '', dest:   '', destSuggestions:   [],
    newAddress:  '',             addressSuggestions: [],
    addresses:   [],
    fixedFirst:  null,
    fixedLast:   null,
    showAddInput:    false,
    helpOpen:        false,
    drawerOpen:      false,
    userMenuOpen:    false,
    user:            null,
    stopActionsOpen: false,
    importOpen:      false,
    importType:      'csv',
    importFile:      null,
    newDescription:  '',
    editingIndex:    null,
    editAddress:     '',
    editDescription: '',
    locationHint:    null,
    loading:        false,
    geolocating:    false,
    copied:         false,
    shared:         false,
    saved:          false,
    canNativeShare: typeof navigator !== 'undefined' && typeof navigator.share === 'function',
    result:         null,
    mapPath:        null,
    mapImageUrl:    null,
    _mapPathGen:    0,
    error:          '',
    notice:         '',
    clearConfirmOpen: false,

    init() {
      const params    = new URLSearchParams(location.search);
      const urlOrigin = params.get('origin');
      const urlDest   = params.get('dest');
      const urlAddrs  = params.getAll('a');
      const urlSaved  = params.get('saved');

      if (urlSaved) {
        fetch(`/api/v1/routes/saved/${urlSaved}`)
          .then(r => r.ok ? r.json() : null)
          .then(data => { if (data) this.result = data; });
        history.replaceState(null, '', location.pathname);
      } else if (params.get('expired') === '1') {
        this.notice = 'Este link expirou. Os roteiros compartilhados ficam disponíveis apenas enquanto o servidor estiver ativo. Crie uma nova rota abaixo.';
        setTimeout(() => { this.notice = ''; }, 5000);
        history.replaceState(null, '', location.pathname);
      } else if (urlOrigin || urlDest || urlAddrs.length) {
        if (urlOrigin) { this.origin = urlOrigin; this.originInput = urlOrigin; }
        if (urlDest)   { this.dest   = urlDest;   this.destInput   = urlDest; }
        if (urlAddrs.length) this.addresses = urlAddrs.map(a => ({ address: a, description: '' }));
        history.replaceState(null, '', location.pathname);
      } else {
        const saved = localStorage.getItem('routeApp');
        if (saved) {
          try {
            const d = JSON.parse(saved);
            this.origin      = d.origin      ?? '';
            this.originInput = d.originInput ?? '';
            this.dest        = d.dest        ?? '';
            this.destInput   = d.destInput   ?? '';
            this.addresses   = (d.addresses ?? []).map(a =>
              typeof a === 'string' ? { address: a, description: '' } : a
            );
            this.fixedFirst  = d.fixedFirst  ?? null;
            this.fixedLast   = d.fixedLast   ?? null;
          } catch (_) {}
        }
      }

      const save = () => localStorage.setItem('routeApp', JSON.stringify({
        origin:      this.origin,
        originInput: this.originInput,
        dest:        this.dest,
        destInput:   this.destInput,
        addresses:   this.addresses,
        fixedFirst:  this.fixedFirst,
        fixedLast:   this.fixedLast,
      }));

      this.$watch('origin',      save);
      this.$watch('originInput', save);
      this.$watch('dest',        save);
      this.$watch('destInput',   save);
      this.$watch('addresses',   save);
      this.$watch('fixedFirst',  save);
      this.$watch('fixedLast',   save);
    },

    async fetchSuggestions(field, value) {
      if (value.trim().length < 3) {
        this[field + 'Suggestions'] = [];
        return;
      }
      try {
        const params = new URLSearchParams({ q: value });
        if (this.locationHint) {
          params.set('lat', this.locationHint.lat);
          params.set('lng', this.locationHint.lng);
        }
        const res = await fetch('/api/v1/autocomplete?' + params.toString());
        const data = await res.json();
        this[field + 'Suggestions'] = data.suggestions ?? [];
      } catch (_) {
        this[field + 'Suggestions'] = [];
      }
    },

    setOrigin() {
      const v = this.originInput.trim();
      if (v) { this.origin = v; this.originSuggestions = []; this.setLocationHint(v); }
    },
    setDest() {
      const v = this.destInput.trim();
      if (v) { this.dest = v; this.destSuggestions = []; this.setLocationHint(v); }
    },

    setLocationHint(address) {
      if (this.locationHint || !address) return;
      fetch('/api/v1/geocode?q=' + encodeURIComponent(address))
        .then(r => r.ok ? r.json() : null)
        .then(data => { if (data) this.locationHint = { lat: data.lat, lng: data.lng }; })
        .catch(() => {});
    },

    toggleFirst(addr) {
      this.fixedFirst = this.fixedFirst === addr ? null : addr;
      if (this.fixedLast === addr) this.fixedLast = null;
    },
    toggleLast(addr) {
      this.fixedLast = this.fixedLast === addr ? null : addr;
      if (this.fixedFirst === addr) this.fixedFirst = null;
    },

    openAddInput() {
      this.showAddInput = true;
      this.$nextTick(() => { this.$refs.addInput?.focus(); });
    },

    addAddress() {
      const v = this.newAddress.trim();
      if (v) {
        this.addresses.push({ address: v, description: this.newDescription.trim() });
        this.setLocationHint(v);
        this.newAddress = '';
        this.newDescription = '';
        this.addressSuggestions = [];
        this.showAddInput = false;
      }
    },

    streetPart(address) {
      const idx = address.indexOf(' - ');
      return idx > 0 ? address.substring(0, idx).trim() : address;
    },
    restPart(address) {
      const idx = address.indexOf(' - ');
      return idx > 0 ? address.substring(idx + 3).trim() : '';
    },

    startEdit(i) {
      this.editingIndex    = i;
      this.editAddress     = this.addresses[i].address;
      this.editDescription = this.addresses[i].description;
    },
    saveEdit(i) {
      const v = this.editAddress.trim();
      if (!v) return;
      if (this.fixedFirst === this.addresses[i].address) this.fixedFirst = v;
      if (this.fixedLast  === this.addresses[i].address) this.fixedLast  = v;
      this.addresses[i] = { address: v, description: this.editDescription.trim() };
      this.editingIndex = null;
    },
    cancelEdit() { this.editingIndex = null; },

    _mapProject(pts, bbox) {
      const W = 460, H = 160, PAD = 28;
      const src = bbox || pts;
      const lats = src.map(p => p.lat), lngs = src.map(p => p.lng);
      const minLat = Math.min(...lats), maxLat = Math.max(...lats);
      const minLng = Math.min(...lngs), maxLng = Math.max(...lngs);
      const latRange = maxLat - minLat || 0.01;
      const lngRange = maxLng - minLng || 0.01;
      const cosLat = Math.cos((minLat + maxLat) / 2 * Math.PI / 180);
      const scaleX = (W - 2 * PAD) / (lngRange * cosLat);
      const scaleY = (H - 2 * PAD) / latRange;
      const scale  = Math.min(scaleX, scaleY);
      const offX   = (W - 2 * PAD - lngRange * cosLat * scale) / 2;
      const offY   = (H - 2 * PAD - latRange * scale) / 2;
      return pts.map(p => ({
        ...p,
        x: PAD + offX + (p.lng - minLng) * cosLat * scale,
        y: H - PAD - offY - (p.lat - minLat) * scale,
      }));
    },
    _stopPins() {
      if (!this.result) return [];
      const raw = [];
      if (this.result.origin) raw.push({ ...this.result.origin.coordinates, type: 'origin' });
      for (const s of this.result.optimized_route)
        raw.push({ ...s.coordinates, type: 'stop', order: s.order });
      if (this.result.destination) raw.push({ ...this.result.destination.coordinates, type: 'dest' });
      return raw;
    },
    mapPoints() {
      const pins = this._stopPins();
      if (!pins.length) return [];
      return this._mapProject(pins);
    },
    mapPolyline() {
      const pins = this._stopPins();
      if (!pins.length) return '';
      if (this.mapPath && this.mapPath.length >= 2) {
        const projected = this._mapProject(this.mapPath, pins);
        return projected.map(p => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
      }
      return this._mapProject(pins).map(p => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
    },
    async _fetchMapPath(gen) {
      if (!this.result) return;
      const pins = this._stopPins();
      if (pins.length < 2) return;
      const points = pins.map(p => ({ lat: p.lat, lng: p.lng }));
      try {
        const res = await fetch('/api/v1/routes/polyline', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ points }),
        });
        if (!res.ok) return;
        const data = await res.json();
        if (this._mapPathGen !== gen) return;
        this.mapPath = data.path;
        await this._fetchMapImage(gen, data.encoded_polyline);
      } catch (_) {}
    },
    async _fetchMapImage(gen, encodedPolyline) {
      if (!this.result) return;
      const pins = this._stopPins();
      if (pins.length < 2) return;
      const first = pins[0], last = pins[pins.length - 1];
      try {
        const res = await fetch('/api/v1/routes/map-image', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            encoded_polyline: encodedPolyline ?? null,
            origin:      { lat: first.lat, lng: first.lng },
            destination: { lat: last.lat,  lng: last.lng  },
          }),
        });
        if (!res.ok || this._mapPathGen !== gen) return;
        const blob = await res.blob();
        if (this._mapPathGen !== gen) return;
        if (this.mapImageUrl) URL.revokeObjectURL(this.mapImageUrl);
        this.mapImageUrl = URL.createObjectURL(blob);
      } catch (_) {}
    },
    cancelAddAddress() {
      this.newAddress = '';
      this.newDescription = '';
      this.addressSuggestions = [];
      this.showAddInput = false;
    },

    getStopInfo(address) {
      return this.addresses.find(a => a.address === address) ?? { address, description: '' };
    },
    formatDuration(min) {
      if (!min) return null;
      if (min < 60) return Math.round(min) + ' min';
      const h = Math.floor(min / 60), m = Math.round(min % 60);
      return m > 0 ? `${h}h ${m}min` : `${h}h`;
    },

    confirmClearAll() {
      const hasContent = this.addresses.length > 0 || this.origin || this.dest || this.result;
      if (!hasContent) { this.clearAll(); return; }
      this.clearConfirmOpen = true;
    },

    async saveAndClear() {
      await this.saveRoute();
      this.clearConfirmOpen = false;
      this.clearAll();
    },

    clearAll() {
      this.origin = ''; this.originInput = ''; this.originSuggestions = [];
      this.dest   = ''; this.destInput   = ''; this.destSuggestions   = [];
      this.newAddress = ''; this.addressSuggestions = [];
      this.addresses = [];
      this.fixedFirst = null;
      this.fixedLast  = null;
      this.showAddInput = false;
      this.newDescription = '';
      this.locationHint = null;
      this.result = null;
      this.mapPath = null;
      if (this.mapImageUrl) { URL.revokeObjectURL(this.mapImageUrl); this.mapImageUrl = null; }
      this._mapPathGen = 0;
      this.error  = '';
      localStorage.removeItem('routeApp');
    },

    async geolocate() {
      if (!navigator.geolocation) {
        this.error = 'Geolocalização não suportada pelo navegador.';
        return;
      }
      this.geolocating = true;
      this.error = '';
      navigator.geolocation.getCurrentPosition(
        async (pos) => {
          try {
            const { latitude: lat, longitude: lng } = pos.coords;
            this.locationHint = { lat, lng };
            const res = await fetch(`/api/v1/reverse?lat=${lat}&lng=${lng}`);
            if (!res.ok) throw new Error();
            const data = await res.json();
            this.originInput = data.address;
            this.origin = data.address;
            this.originSuggestions = [];
          } catch (_) {
            this.error = 'Não foi possível obter o endereço da sua localização.';
          } finally {
            this.geolocating = false;
          }
        },
        () => {
          this.error = 'Permissão de localização negada ou não disponível.';
          this.geolocating = false;
        }
      );
    },

    async shareRoute() {
      let shareUrl = location.origin;
      try {
        const res = await fetch('/api/v1/shorten', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            addresses: this.addresses.map(a => a.address),
            ...(this.origin && { origin: this.origin }),
            ...(this.dest   && { destination: this.dest }),
          }),
        });
        if (res.ok) {
          const data = await res.json();
          shareUrl = `${location.origin}${data.path}`;
        }
      } catch (_) {}

      const msg = 'Veja os endereços que separei para você — clique em otimizar para encontrar a melhor rota!';
      const shareData = { title: 'Rota — Find My Route', text: msg, url: shareUrl };
      if (navigator.share && navigator.canShare?.(shareData)) {
        navigator.share(shareData).catch(() => {});
      } else {
        navigator.clipboard.writeText(`${msg}\n${shareUrl}`).then(() => {
          this.shared = true;
          setTimeout(() => { this.shared = false; }, 2000);
        });
      }
    },

    copyRoute() {
      if (!this.result) return;
      const lines = [`Rota otimizada — ${this.result.total_distance_km} km`, ''];
      if (this.result.origin) lines.push(`0. ${this.result.origin.address} (origem)`);
      for (const stop of this.result.optimized_route) {
        const item = this.addresses.find(a => a.address === stop.original_address);
        const label = item?.description ? `${item.description} — ` : '';
        lines.push(`${stop.order}. ${label}${stop.original_address}`);
      }
      if (this.result.destination) lines.push(`F. ${this.result.destination.address} (destino)`);
      lines.push('', 'Rota otimizada com findmyroute.com.br');
      navigator.clipboard.writeText(lines.join('\n')).then(() => {
        this.copied = true;
        setTimeout(() => { this.copied = false; }, 2000);
      });
    },

    async saveRoute() {
      if (!this.result) return;
      try {
        const res = await fetch('/api/v1/routes/save', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            result: this.result,
            inputs: {
              addresses: this.addresses.map(a => a.address),
              ...(this.origin && { origin: this.origin }),
              ...(this.dest   && { destination: this.dest }),
            },
          }),
        });
        if (!res.ok) return;
        const data = await res.json();

        const history = JSON.parse(localStorage.getItem('savedRoutes') || '[]');
        history.unshift({
          code:       data.code,
          total_km:   this.result.total_distance_km,
          stops:      this.result.optimized_route.length,
          created_at: new Date().toISOString(),
        });
        localStorage.setItem('savedRoutes', JSON.stringify(history.slice(0, 50)));

        this.saved = true;
        setTimeout(() => { this.saved = false; }, 2000);
      } catch (_) {}
    },

    async optimize() {
      this.error  = '';
      this.result = null;
      this.loading = true;

      const body = { addresses: this.addresses.map(a => a.address) };
      if (this.origin)     body.origin      = this.origin;
      if (this.dest)       body.destination = this.dest;
      if (this.fixedFirst) body.fixed_first = this.fixedFirst;
      if (this.fixedLast)  body.fixed_last  = this.fixedLast;

      try {
        const res = await fetch('/api/v1/routes/optimize', {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify(body),
        });
        const data = await res.json();
        if (!res.ok) {
          this.error = data.detail ?? `Erro ${res.status}`;
        } else {
          this.result = data;
          this.mapPath = null;
          const gen = ++this._mapPathGen;
          this._fetchMapPath(gen);
          this.$nextTick(() => {
            const el = document.querySelector('.result-section');
            if (el) window.scrollTo({ top: el.getBoundingClientRect().top + window.pageYOffset - 16, behavior: 'smooth' });
          });
        }
      } catch (e) {
        this.error = 'Erro de conexão com a API.';
      } finally {
        this.loading = false;
      }
    },
  };
}
