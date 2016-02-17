# OJO Bot

This is a prototype data processor/publisher for NASA. 

Pat Cappelaere	Vightel		pat@cappelaere.com

## Requirements & Installation

npm install

## Set  Env	
Edit the env.template file and source it


## Local Docker
Install docker and start VM
Start Docker VM via Docker Quickstart Terminal
> docker-machine env default
> bash
> eval "$(docker-machine env default)"
> docker ps

### Building base container
> docker-compose build conda
Test it:
> docker-compose run conda

Tag it
> docker images
> docker tag 608fd2eb4b79 cappelaere/ojo_publisher_base_stack:v1

Push it
> docker login
> docker push cappelaere/ojo_publisher_base_stack

### Build locally
> docker-compose build development

Start shell
> docker-compose run development		!Note: does not work since there is no port mapping
> docker run -i -p 8080:8080 -t ojobot_development /bin/bash	!Note: Seems to work with curl -i 192.168.99.100:8080
> docker-compose up development			!Note: postgres connection problem


### Checking/Cleaning docker images
> docker images

Clean Docker
> docker rm -v $(docker ps -a -q -f status=exited)
> docker rmi -f $(docker images | grep "<none>" | awk "{print \$3}")
> docker rmi $(docker images -f "dangling=true" -q)

### Convox
#### Pre-requisites
Create an Amazon SQS Queue
and Update Environment variables

Lambda functions for scheduling python scripts

Postgresql database to host sessions and landslide inventory

Install new rack from GUI (Takes a while)

Enable SSH
> convox instances keyroll

Check
> convox instances

Scale Up
> convox rack scale --type m3.large

> convox scale web --count 1 

> convox scale web --memory 512

> convox scale worker --count 1 

> convox scale worker --memory 512

Create App
> convox apps create ojo-bot

Check
> convox apps info

> convox instances

Deploy
> convox deploy

Check logs
> convox logs


