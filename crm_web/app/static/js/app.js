// Interacciones mínimas: desplegar filas y enviar filtros al cambiar un select.
function alternar(id) {
  const fila = document.getElementById(id);
  if (fila) fila.hidden = !fila.hidden;
}

document.addEventListener('DOMContentLoaded', () => {
  // Los filtros con select se aplican solos al cambiarlos.
  document.querySelectorAll('form.filtros select').forEach(sel => {
    sel.addEventListener('change', () => sel.form.submit());
  });
  // El mensaje de aviso desaparece de la URL al recargar.
  if (location.search.includes('aviso=')) {
    const url = new URL(location.href);
    url.searchParams.delete('aviso');
    url.searchParams.delete('t');
    history.replaceState({}, '', url.pathname + (url.search === '?' ? '' : url.search));
  }
});
