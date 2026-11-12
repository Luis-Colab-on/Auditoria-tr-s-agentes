# The package version must match the image browser version.
FROM mcr.microsoft.com/playwright:v1.64.1-noble
WORKDIR /opt/browser
RUN npm install --ignore-scripts --no-audit --no-fund --save-exact playwright@1.64.1
ENV NODE_PATH=/opt/browser/node_modules
USER pwuser
