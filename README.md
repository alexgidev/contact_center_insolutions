
````md
# Contact Center - Docker Demo

## Clonar el repositorio

```bash
git clone https://github.com/alexgidev/contact_center_insolutions.git
cd contact_center_insolutions
````

## Configurar variables de entorno

Copiar el archivo de ejemplo:

```bash
cp .env.docker.example .env.docker
```

## Levantar los contenedores

```bash
docker compose up -d mysql redis adminer api webhook
```

## Verificar que los servicios están activos

```bash
docker compose ps
```

Comprobar logs en tiempo real:

```bash
docker compose logs -f api
docker compose logs -f webhook
```

Adminer disponible en [http://localhost:8080](http://localhost:8080)

* Usuario: `contact_center_user`
* Contraseña: `contact_center_pass`
* Base de datos: `contact_center_db`

## Ejecutar el simulador

Abrir otra terminal y ejecutar dentro del contenedor de la API:

```bash
docker compose exec api python simulator.py
```

Los logs del simulador se mostrarán en esta terminal. Los logs del webhook y de la API se ven en las otras terminales.

## Reiniciar servicios

```bash
docker compose restart api
docker compose restart webhook
```

Para detener todo y eliminar datos persistentes:

```bash
docker compose down -v
```

