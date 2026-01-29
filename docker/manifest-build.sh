#!/bin/bash
## Usage:
# ./manifest-build [version] [amd64] [arm64] [riscv64]
# provide the version of the build, plus each of the architectures that are available.  A manifest will be created using [docker-image]:[version] and [docker-image]:latest

source ./vars.sh
VERSION="$1"

MANIFEST_LIST_VER=""
MANIFEST_LIST_LATEST=""

for arg in "$@"; do
        if [[ "$arg" != "$1" ]]; then
                # skip the 1st arg that should be the version
                MANIFEST_LIST_VER+="$REGISTRY/$PACKAGE:${VERSION}-${arg} "
                MANIFEST_LIST_LATEST+="$REGISTRY/$PACKAGE:latest-${arg} "
        fi
done

echo Building the version manifest for "$REGISTRY/$PACKAGE:${VERSION}"...
docker manifest create $REGISTRY/$PACKAGE:${VERSION} $MANIFEST_LIST_VER
if [[ $? != 0 ]]; then exit 1; fi
echo Building the version manifest for "$REGISTRY/$PACKAGE:latest"...
docker manifest create $REGISTRY/$PACKAGE:latest $MANIFEST_LIST_LATEST
if [[ $? != 0 ]]; then exit 1; fi

while true; do
        read -p "Do you want to push the manifest to docker hub? [Y/n] " yn
        case $yn in
                [Yy]* ) echo "Pushing manifest "$REGISTRY/$PACKAGE:${VERSION}" to docker..."
                        docker manifest push $REGISTRY/$PACKAGE:${VERSION}
                        echo "Pushing manifest "$REGISTRY/$PACKAGE:latest" to docker..."
                        docker manifest push $REGISTRY/$PACKAGE:latest
                        break;;
                [Nn]* ) echo "Cancelling push to docker..."
                        exit 0;;
        esac
done

