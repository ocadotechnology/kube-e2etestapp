FROM mirror-hub.docker.tech.lastmile.com/python:3.5-alpine
RUN apk --no-cache add curl
RUN mkdir -p /app/kubee2etests/frontend/static/css && \
     mkdir -p /app/kubee2etests/frontend/static/js && \
     curl https://maxcdn.bootstrapcdn.com/bootstrap/3.3.2/css/bootstrap.min.css > /app/kubee2etests/frontend/static/css/bootstrap-3.3.2.min.css && \
     curl https://maxcdn.bootstrapcdn.com/bootstrap/3.3.2/js/bootstrap.min.js > /app/kubee2etests/frontend/static/js/bootstrap-3.3.2.min.js && \
     curl https://ajax.googleapis.com/ajax/libs/jquery/1.12.4/jquery.min.js > /app/kubee2etests/frontend/static/js/jquery-1.12.4.min.js
COPY . ./app
WORKDIR /app
ENV PYTHONPATH "$PYTHONPATH:/app"
RUN pip install --no-cache -r requirements.txt
