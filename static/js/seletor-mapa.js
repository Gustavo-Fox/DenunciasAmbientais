/* Seletor de local: mapa clicável que preenche latitude e longitude (telas de cadastro e edição).
   Lê o centro e o zoom dos atributos data-* da div #map. */
(function () {
  var el = document.getElementById('map');
  var m = L.map(el).setView([+el.dataset.lat, +el.dataset.lon], +el.dataset.zoom), k = null;
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {attribution: '© OpenStreetMap'}).addTo(m);
  var lat = document.getElementById('lat'), lon = document.getElementById('lon');
  if (el.dataset.marcador) k = L.marker([+el.dataset.lat, +el.dataset.lon]).addTo(m);
  function marcar(a, b, zoom) {
    lat.value = a.toFixed(6); lon.value = b.toFixed(6);
    if (k) k.setLatLng([a, b]); else k = L.marker([a, b]).addTo(m);
    if (zoom) m.setView([a, b], zoom);
  }
  m.on('click', function (e) { marcar(e.latlng.lat, e.latlng.lng); });
  window.gps = function () {
    navigator.geolocation.getCurrentPosition(
      function (p) { marcar(p.coords.latitude, p.coords.longitude, 16); },
      function () { alert('Não foi possível obter a localização.'); });
  };
})();
