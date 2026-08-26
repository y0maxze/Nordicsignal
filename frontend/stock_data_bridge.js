(function(){
  // stock.html intentionally keeps its canonical state in a global lexical `let data`.
  // Global lexical bindings are shared between classic scripts, but unlike `var` they
  // are not properties on `window`. Enhanced stock panels historically read
  // `window.data`, which made Insider render an empty object even when /api/insider
  // returned live rows. Publish the same object reference once; Object.assign() in
  // stock.html keeps this reference current as the parallel API requests finish.
  try {
    if (typeof data !== 'undefined' && data && typeof data === 'object') {
      window.data = data;
    }
  } catch (error) {
    console.warn('NordicSignal stock data bridge unavailable', error);
  }
})();
