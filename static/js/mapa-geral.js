/* Mapa geral: um marcador por denúncia com coordenadas (dados em <script id="pontos">). */
(function () {
  var el = document.getElementById('map');
  var m = L.map(el).setView([+el.dataset.lat, +el.dataset.lon], +el.dataset.zoom);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {attribution: '© OpenStreetMap'}).addTo(m);
  JSON.parse(document.getElementById('pontos').textContent).forEach(function (p) {
    var a = document.createElement('a'); a.href = '/d/' + p.id; a.textContent = p.codigo;
    var b = document.createElement('div'); b.append(a, ' · ' + (p.cat || '') + ' · ' + p.status);
    L.marker([p.lat, p.lon]).addTo(m).bindPopup(b);
  });
})();
