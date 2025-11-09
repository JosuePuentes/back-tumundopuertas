/**
 * Configuración de consola para producción
 * Deshabilita logs de debug en producción para mejorar el rendimiento
 */
export const configureConsole = () => {
  if (import.meta.env.PROD) {
    // Guardar funciones originales por si acaso
    const originalLog = console.log;
    const originalDebug = console.debug;
    const originalInfo = console.info;
    
    // Función para mostrar mensaje informativo una sola vez
    let messageShown = false;
    const showMessage = () => {
      if (!messageShown) {
        const style = `
          font-size: 16px;
          font-weight: bold;
          color: #2563eb;
          text-align: center;
          padding: 12px;
          background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
          border: 2px solid #2563eb;
          border-radius: 8px;
          margin: 10px 0;
        `;
        originalLog('%c🔒 LOGS DESHABILITADOS EN PRODUCCIÓN', style);
        originalLog('%cLos logs de desarrollo están deshabilitados para mejorar el rendimiento.', 'font-size: 12px; color: #666;');
        messageShown = true;
      }
    };
    
    // Interceptar console.log
    console.log = function(...args: any[]) {
      showMessage();
      // No mostrar nada más
    };
    
    // Interceptar console.debug
    console.debug = function() {};
    
    // Interceptar console.info
    console.info = function() {};
    
    // Mantener console.error y console.warn para errores importantes
    // Estos se mantienen activos para debugging de errores críticos
  }
};

