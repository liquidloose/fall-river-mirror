# FastAPI, Docker, and WordPress dev environment for The Fall River Mirror

## Getting Started

Change the name of the file `.env.sample` to `.env` and adjust the values accordingly.

In order to run this project, you will need to create two images with Docker.

### Building Docker Images

The first one is the WordPress image. To build, use the following command:
```bash
docker build -t fr-mirror .
```

The second image you need to create is for the Python API. To build this one, enter the
following command:
```bash
docker build -f Dockerfile.ai -t fr-mirror-ai .
```

### Running the Environment

Now you are ready to create the environment! Type `docker compose up` in your terminal from inside the directory where the Dockerfiles live. The sites will be available at localhost running on the ports that you specified in your .env file: `<your-ip/localhost-goes-here>:<your-port-number-goes-here>`

## Helpful Tips

### Server Reload Command

Use this command to reload the server from inside the container: 
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --log-level info
```

### Log Levels

Here are the log levels:
1. **debug**: Shows the most detailed information, useful for development and troubleshooting
2. **info**: (Default) Shows general operational information
3. **warning**: Shows only warning and error messages
4. **error**: Shows only error messages
5. **critical**: Shows only critical error messages


# FastAPI, Docker, and WordPress dev environment for The Fall River Mirror

## Getting Started

Change the name of the file `.env.sample` to `.env` and adjust the values accordingly.

In order to run this project, you will need to create two images with Docker.

### Building Docker Images

The first one is the WordPress image. To build, use the following command:
```bash
docker build -t fr-mirror .
```

The second image you need to create is for the Python API. To build this one, enter the
following command:
```bash
docker build -f Dockerfile.ai -t fr-mirror-ai .
```

### Running the Environment

Now you are ready to create the environment! Type `docker compose up` in your terminal from inside the directory where the Dockerfiles live. The sites will be available at localhost running on the ports that you specified in your .env file: `<your-ip/localhost-goes-here>:<your-port-number-goes-here>`

## Helpful Tips

### Server Reload Command

Use this command to reload the server from inside the container: 
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --log-level info
```

### Log Levels

Here are the log levels:
1. **debug**: Shows the most detailed information, useful for development and troubleshooting
2. **info**: (Default) Shows general operational information
3. **warning**: Shows only warning and error messages
4. **error**: Shows only error messages
5. **critical**: Shows only critical error messages


### Imports cannot be found
If the ms-python language support displays red, squiggly lines underneath the imports and says something like 
"import can't be found", then run this command:
`which python`
if the output is anything besides 3.13, then you need to change your language interpreter the 3.13 one in VScode/Cursor.


