;(function () {
  var stored = null
  try {
    stored = window.localStorage.getItem('scraper:theme')
  } catch (error) {
    stored = null
  }
  var isDark =
    stored === 'dark' ||
    (stored !== 'light' && window.matchMedia('(prefers-color-scheme: dark)').matches)
  var theme = isDark ? 'dark' : 'light'
  document.documentElement.dataset.theme = theme
  document.documentElement.style.colorScheme = theme
})()
