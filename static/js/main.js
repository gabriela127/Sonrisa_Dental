
async function comprobarConexion() {
  const mensaje = document.getElementById("connection-message");
  const insignia = document.getElementById("connection-badge");

  // Si la página actual no tiene estos elementos, no hacemos nada.
  if (!mensaje || !insignia) {
    return;
  }

  try {
    const respuesta = await fetch("/api/estado", {
      method: "GET",
      headers: {
        "Accept": "application/json"
      }
    });

    const tipoContenido = respuesta.headers.get("content-type") || "";

    if (!tipoContenido.includes("application/json")) {
      throw new Error("El servidor devolvió una respuesta inesperada.");
    }

    const datos = await respuesta.json();

    if (respuesta.ok && datos.mysql === "conectado") {
      mensaje.textContent =
        `MySQL conectado correctamente a la base de datos "${datos.base_datos}".`;

      insignia.textContent = "Conectado";
      insignia.className = "connection-badge ok";
    } else {
      mensaje.textContent =
        datos.mensaje ||
        "La aplicación responde, pero no se pudo conectar con MySQL.";

      insignia.textContent = "Revisar conexión";
      insignia.className = "connection-badge fail";
    }
  } catch (error) {
    mensaje.textContent =
      error.message ||
      "No se pudo consultar el estado. Verifica que Flask esté ejecutándose.";

    insignia.textContent = "Sin respuesta";
    insignia.className = "connection-badge fail";
  }
}

document.addEventListener("DOMContentLoaded", comprobarConexion);

