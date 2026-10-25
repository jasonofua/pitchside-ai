// Everything Pitchside AI runs on, in one resource group. Apps authenticate with one
// user-assigned managed identity; no keys or connection strings are handed out.
param environmentName string
param location string
param tags object
param principalId string
param deployFoundry bool
param foundryEndpoint string
param foundryLocation string
param modelLarge string
param modelLargeVersion string
param modelSmall string
param modelSmallVersion string
param modelCapacity int
param webPubSubSku string
param budgetEmail string
param budgetAmount int
param budgetStartDate string
@description('Images azd last deployed, by service name (empty before the first deploy).')
param serviceImages object

var token = toLower(uniqueString(subscription().id, resourceGroup().id, environmentName))
var prefix = 'ps${take(token, 8)}'
var topics = ['matches', 'events', 'tracking', 'accepted', 'stats', 'triggers', 'overlays', 'trace', 'control']
// Which service reads which topic: one consumer group per reader.
var consumerGroups = {
  matches: ['stats', 'ingestor', 'gateway']
  events: ['ingestor']
  tracking: ['stats', 'gateway']
  accepted: ['stats', 'gateway']
  stats: ['gateway']
  triggers: ['agents']
  overlays: ['gateway']
  trace: ['gateway']
  control: ['sim', 'agents']
}
var groupsFlat = flatten(map(topics, t => map(consumerGroups[t], g => { topic: t, group: g })))

// Built-in roles
var roles = {
  acrPull: '7f951dda-4ed3-4680-a7ca-43fe172d538d'
  eventHubsDataOwner: 'f526a384-b230-433a-b45c-95f59c4a2dec'
  webPubSubOwner: '12cf5a90-567b-43ae-8102-96cf46c7d9b4'
  keyVaultSecretsUser: '4633458b-17de-408a-b874-0445c86b69e6'
  cognitiveServicesOpenAIUser: '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
  azureAIUser: '53ca6127-db72-4b80-b1b0-d745d6d5456d'
  monitoringMetricsPublisher: '3913510d-42f4-4e42-8a64-420c390055eb'
}

// ---------------------------------------------------------------- identity, logs, registry

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${prefix}'
  location: location
  tags: tags
}

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${prefix}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${prefix}'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logs.id
    DisableLocalAuth: true
  }
}

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: 'cr${prefix}'
  location: location
  tags: tags
  sku: { name: 'Basic' }
  properties: { adminUserEnabled: false }
}

// ------------------------------------------------------------------------- Event Hubs

resource eventHubs 'Microsoft.EventHub/namespaces@2024-01-01' = {
  name: 'evh-${prefix}'
  location: location
  tags: tags
  sku: { name: 'Standard', tier: 'Standard', capacity: 1 }
  properties: {
    disableLocalAuth: true
    minimumTlsVersion: '1.2'
  }
}

resource hubs 'Microsoft.EventHub/namespaces/eventhubs@2024-01-01' = [for t in topics: {
  parent: eventHubs
  name: t
  properties: {
    partitionCount: 2
    messageRetentionInDays: 1
  }
}]

resource groups 'Microsoft.EventHub/namespaces/eventhubs/consumergroups@2024-01-01' = [for (cg, i) in groupsFlat: {
  name: '${eventHubs.name}/${cg.topic}/${cg.group}'
  dependsOn: [hubs]
}]

// ---------------------------------------------------------------------------- Cosmos DB

resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' = {
  name: 'cosmos-${prefix}'
  location: location
  tags: tags
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    locations: [{ locationName: location, failoverPriority: 0 }]
    capabilities: [{ name: 'EnableServerless' }]
    disableLocalAuth: true
    consistencyPolicy: { defaultConsistencyLevel: 'Session' }
  }
}

resource cosmosDb 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-05-15' = {
  parent: cosmos
  name: 'pitchside'
  properties: { resource: { id: 'pitchside' } }
}

resource cosmosContainers 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = [for name in ['events', 'matches', 'docs']: {
  parent: cosmosDb
  name: name
  properties: {
    resource: {
      id: name
      partitionKey: { paths: ['/match_id'], kind: 'Hash' }
      defaultTtl: 2592000 // matches are demo material: keep 30 days
    }
  }
}]

// Built-in "Cosmos DB Built-in Data Contributor" (data plane).
resource cosmosDataApps 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-05-15' = {
  parent: cosmos
  name: guid(cosmos.id, identity.id, 'data-contributor')
  properties: {
    roleDefinitionId: '${cosmos.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002'
    principalId: identity.properties.principalId
    scope: cosmos.id
  }
}

resource cosmosDataUser 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-05-15' = if (!empty(principalId)) {
  parent: cosmos
  name: guid(cosmos.id, principalId, 'data-contributor')
  properties: {
    roleDefinitionId: '${cosmos.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002'
    principalId: principalId
    scope: cosmos.id
  }
}

// --------------------------------------------------------------------------- Web PubSub

resource webPubSub 'Microsoft.SignalRService/webPubSub@2024-03-01' = {
  name: 'wps-${prefix}'
  location: location
  tags: tags
  sku: { name: webPubSubSku, capacity: 1 }
  properties: {
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
  }
}

resource webPubSubHub 'Microsoft.SignalRService/webPubSub/hubs@2024-03-01' = {
  parent: webPubSub
  name: 'pitchside'
  properties: { anonymousConnectPolicy: 'deny' }
}

// ---------------------------------------------------------------------------- Key Vault

resource vault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: 'kv-${prefix}'
  location: location
  tags: tags
  properties: {
    tenantId: subscription().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
  }
}

// The simulator CLI's --sink ws needs this token to stream into the deployed gateway.
resource ingestToken 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: vault
  name: 'ingest-token'
  properties: { value: guid(vault.id, 'ingest-token', token) }
}

// ------------------------------------------------------------------------------ Foundry

resource foundry 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = if (deployFoundry) {
  name: 'ai-${prefix}'
  location: foundryLocation
  tags: tags
  kind: 'AIServices'
  sku: { name: 'S0' }
  identity: { type: 'SystemAssigned' }
  properties: {
    customSubDomainName: 'ai-${prefix}'
    allowProjectManagement: true
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
  }
}

resource foundryProject 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' = if (deployFoundry) {
  parent: foundry
  name: 'pitchside'
  location: foundryLocation
  identity: { type: 'SystemAssigned' }
  properties: {
    displayName: 'Pitchside AI'
    description: 'Agents for live, explained, personalized match intelligence.'
  }
}

resource largeDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = if (deployFoundry) {
  parent: foundry
  name: modelLarge
  sku: { name: 'GlobalStandard', capacity: modelCapacity }
  properties: {
    model: { format: 'OpenAI', name: modelLarge, version: modelLargeVersion }
  }
}

resource smallDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = if (deployFoundry) {
  parent: foundry
  name: modelSmall
  sku: { name: 'GlobalStandard', capacity: modelCapacity }
  properties: {
    model: { format: 'OpenAI', name: modelSmall, version: modelSmallVersion }
  }
  dependsOn: [largeDeployment] // deployments on one account are created one at a time
}

// The project endpoint is derived from names, so it is known before the account exists.
var foundryProjectEndpoint = deployFoundry
  ? 'https://ai-${prefix}.services.ai.azure.com/api/projects/pitchside'
  : foundryEndpoint

// ------------------------------------------------------------------------ role grants

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, identity.id, roles.acrPull)
  scope: registry
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.acrPull)
  }
}

resource eventHubsData 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(eventHubs.id, identity.id, roles.eventHubsDataOwner)
  scope: eventHubs
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.eventHubsDataOwner)
  }
}

resource webPubSubData 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(webPubSub.id, identity.id, roles.webPubSubOwner)
  scope: webPubSub
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.webPubSubOwner)
  }
}

resource vaultSecrets 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(vault.id, identity.id, roles.keyVaultSecretsUser)
  scope: vault
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.keyVaultSecretsUser)
  }
}

resource telemetryPublisher 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(appInsights.id, identity.id, roles.monitoringMetricsPublisher)
  scope: appInsights
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.monitoringMetricsPublisher)
  }
}

resource foundryOpenAIUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (deployFoundry) {
  name: guid(resourceGroup().id, identity.id, roles.cognitiveServicesOpenAIUser)
  scope: foundry
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.cognitiveServicesOpenAIUser)
  }
}

resource foundryAIUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (deployFoundry) {
  name: guid(resourceGroup().id, identity.id, roles.azureAIUser)
  scope: foundry
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.azureAIUser)
  }
}

resource foundryAIUserDev 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (deployFoundry && !empty(principalId)) {
  name: guid(resourceGroup().id, principalId, roles.azureAIUser)
  scope: foundry
  properties: {
    principalId: principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.azureAIUser)
  }
}

// ------------------------------------------------------------------------- budget

// Keeps the public demo from being switched off by a billing surprise before judging ends.
resource budget 'Microsoft.Consumption/budgets@2023-11-01' = if (!empty(budgetEmail)) {
  name: 'budget-${prefix}'
  properties: {
    category: 'Cost'
    amount: budgetAmount
    timeGrain: 'Monthly'
    timePeriod: { startDate: budgetStartDate }
    notifications: {
      actual80: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 80
        thresholdType: 'Actual'
        contactEmails: [budgetEmail]
      }
      forecast100: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 100
        thresholdType: 'Forecasted'
        contactEmails: [budgetEmail]
      }
    }
  }
}

// ---------------------------------------------------------------------- Container Apps

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-${prefix}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
  }
}

resource web 'Microsoft.Web/staticSites@2023-12-01' = {
  name: 'swa-${prefix}'
  location: 'westeurope'
  tags: union(tags, { 'azd-service-name': 'web' })
  sku: { name: 'Free', tier: 'Free' }
  properties: {}
}

var statsAppName = 'ca-stats-${prefix}'
var gatewayAppName = 'ca-gateway-${prefix}'
var commonEnv = [
  { name: 'PITCHSIDE_MODE', value: 'azure' }
  { name: 'AZURE_CLIENT_ID', value: identity.properties.clientId }
  { name: 'EVENTHUBS_NAMESPACE', value: '${eventHubs.name}.servicebus.windows.net' }
  { name: 'COSMOS_ENDPOINT', value: cosmos.properties.documentEndpoint }
  { name: 'COSMOS_DATABASE', value: 'pitchside' }
  { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsights.properties.ConnectionString }
  { name: 'FOUNDRY_ENDPOINT', value: foundryProjectEndpoint }
  { name: 'MODEL_LARGE', value: modelLarge }
  { name: 'MODEL_SMALL', value: modelSmall }
  { name: 'PITCHSIDE_MCP_URL', value: 'http://${statsAppName}/mcp' }
  { name: 'PITCHSIDE_STATS_URL', value: 'http://${statsAppName}' }
]

// Every worker keeps per-match state in memory (Stats Engine, agent memory) or forwards
// to browsers (gateway), so each runs exactly one replica; see docs/DECISIONS.md (D27).
module gateway 'modules/app.bicep' = {
  name: 'app-gateway'
  params: {
    name: gatewayAppName
    serviceName: 'gateway'
    role: 'gateway'
    location: location
    tags: tags
    environmentId: environment.id
    identityId: identity.id
    registryServer: registry.properties.loginServer
    ingress: 'external'
    env: concat(commonEnv, [
      { name: 'WEBPUBSUB_ENDPOINT', value: 'https://${webPubSub.properties.hostName}' }
      { name: 'WEBPUBSUB_HUB', value: webPubSubHub.name }
      { name: 'PITCHSIDE_ALLOWED_ORIGINS', value: 'https://${web.properties.defaultHostname}' }
      { name: 'PITCHSIDE_INGEST_TOKEN', secretRef: 'ingest-token' }
    ])
    secrets: [
      { name: 'ingest-token', keyVaultUrl: ingestToken.properties.secretUri, identity: identity.id }
    ]
    imageName: serviceImages.?gateway ?? ''
  }
  // Start after the data-plane grants exist (they can still take minutes to apply).
  dependsOn: [acrPull, vaultSecrets, eventHubsData, webPubSubData, telemetryPublisher, cosmosDataApps, foundryOpenAIUser, foundryAIUser]
}

module stats 'modules/app.bicep' = {
  name: 'app-stats'
  params: {
    name: statsAppName
    serviceName: 'stats'
    role: 'stats'
    location: location
    tags: tags
    environmentId: environment.id
    identityId: identity.id
    registryServer: registry.properties.loginServer
    ingress: 'internal'
    env: commonEnv
    imageName: serviceImages.?stats ?? ''
  }
  dependsOn: [acrPull, eventHubsData, webPubSubData, telemetryPublisher, cosmosDataApps, foundryOpenAIUser, foundryAIUser]
}

module workers 'modules/app.bicep' = [for role in ['sim', 'ingestor', 'agents']: {
  name: 'app-${role}'
  params: {
    name: 'ca-${role}-${prefix}'
    serviceName: role
    role: role
    location: location
    tags: tags
    environmentId: environment.id
    identityId: identity.id
    registryServer: registry.properties.loginServer
    ingress: 'none'
    env: commonEnv
    imageName: serviceImages[?role] ?? ''
  }
  dependsOn: [acrPull, eventHubsData, webPubSubData, telemetryPublisher, cosmosDataApps, foundryOpenAIUser, foundryAIUser]
}]

output registryEndpoint string = registry.properties.loginServer
output registryName string = registry.name
output gatewayUrl string = 'https://${gateway.outputs.fqdn}'
output webUrl string = 'https://${web.properties.defaultHostname}'
output foundryEndpoint string = foundryProjectEndpoint
output eventHubsNamespace string = '${eventHubs.name}.servicebus.windows.net'
output cosmosEndpoint string = cosmos.properties.documentEndpoint
output webPubSubEndpoint string = 'https://${webPubSub.properties.hostName}'
output appInsightsName string = appInsights.name
