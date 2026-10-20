// Pitchside AI on Azure: `azd up` provisions everything here and deploys the apps.
targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name of the azd environment; used to name resources.')
param environmentName string

@minLength(1)
@description('Primary region for all resources.')
param location string

@description('Object id of the user running azd, granted data access for debugging.')
param principalId string = ''

@description('Deploy a Microsoft Foundry resource, project and the two model deployments. Set false to use an existing Foundry project (then set foundryEndpoint).')
param deployFoundry bool = true

@description('Existing Foundry project endpoint, used when deployFoundry is false.')
param foundryEndpoint string = ''

@description('Region for Foundry (model availability varies by region).')
param foundryLocation string = location

@description('Large model: analysis and narration.')
param modelLarge string = 'gpt-4.1'
param modelLargeVersion string = '2025-04-14'

@description('Small model: moment triage, rewrites, translation, checks.')
param modelSmall string = 'gpt-4.1-mini'
param modelSmallVersion string = '2025-04-14'

@description('Tokens-per-minute capacity (thousands) for each model deployment.')
param modelCapacity int = 50

@description('Web PubSub tier. Free_F1 caps at 20 connections and 20k messages a day.')
@allowed(['Free_F1', 'Standard_S1'])
param webPubSubSku string = 'Standard_S1'

var tags = { 'azd-env-name': environmentName, project: 'pitchside-ai' }

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

module resources 'resources.bicep' = {
  name: 'pitchside-resources'
  scope: rg
  params: {
    environmentName: environmentName
    location: location
    tags: tags
    principalId: principalId
    deployFoundry: deployFoundry
    foundryEndpoint: foundryEndpoint
    foundryLocation: foundryLocation
    modelLarge: modelLarge
    modelLargeVersion: modelLargeVersion
    modelSmall: modelSmall
    modelSmallVersion: modelSmallVersion
    modelCapacity: modelCapacity
    webPubSubSku: webPubSubSku
  }
}

output AZURE_LOCATION string = location
output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = resources.outputs.registryEndpoint
output AZURE_CONTAINER_REGISTRY_NAME string = resources.outputs.registryName
output GATEWAY_URL string = resources.outputs.gatewayUrl
output WEB_URL string = resources.outputs.webUrl
output FOUNDRY_ENDPOINT string = resources.outputs.foundryEndpoint
output MODEL_LARGE string = modelLarge
output MODEL_SMALL string = modelSmall
output EVENTHUBS_NAMESPACE string = resources.outputs.eventHubsNamespace
output COSMOS_ENDPOINT string = resources.outputs.cosmosEndpoint
output WEBPUBSUB_ENDPOINT string = resources.outputs.webPubSubEndpoint
output APPLICATIONINSIGHTS_NAME string = resources.outputs.appInsightsName
