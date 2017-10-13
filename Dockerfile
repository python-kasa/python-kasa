####################################################
# Use python 3.x and the latest version of alpine  #
####################################################
FROM python:3-alpine

LABEL maintainer=peter@grainger.xyz

###################################################
# Add all system packages relied upon by python   #
###################################################
RUN apk update && \
    apk add --no-cache gcc \
                       libffi-dev \
                       openssl-dev \
                       libxslt-dev \
                       libxml2-dev \
                       musl-dev \
                       linux-headers

###################################################
# Create somewhere to put the files               #
###################################################
RUN mkdir -p /opt/pyHS100
WORKDIR /opt/pyHS100

###################################################
# Requirements file first to help cache           #
###################################################
COPY requirements.txt .
RUN pip install -r requirements.txt

###################################################
# Install dev dependancies                        #
###################################################
RUN pip install pytest pytest-cov voluptuous typing

###################################################
# Copy over the rest.                             #
###################################################
COPY ./ ./

###################################################
# Install everything to the path                  #
###################################################
RUN python setup.py install

###################################################
# Run tests                                       #
###################################################
CMD pytest
