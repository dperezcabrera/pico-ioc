// Custom JavaScript for pico-ioc documentation

// Add copy button functionality enhancements
document.addEventListener('DOMContentLoaded', function() {
  // Add version warning for outdated pages
  const currentVersion = document.querySelector('.md-version__current');
  if (currentVersion && !currentVersion.textContent.includes('latest')) {
    console.log('Viewing older documentation version');
  }
});
