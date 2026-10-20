// One Pitchside service as a Container App. All services share one image; the role
// environment variable decides what the process runs (see services/runtime/main.py).
param name string
@description('azd service name; azd deploys the built image to the app with this tag.')
param serviceName string
@allowed(['gateway', 'stats', 'sim', 'ingestor', 'agents'])
param role string
param location string
param tags object
param environmentId string
param identityId string
param registryServer string
@allowed(['external', 'internal', 'none'])
param ingress string
param env array
param secrets array = []
param cpu string = '0.5'
param memory string = '1Gi'

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: name
  location: location
  tags: union(tags, { 'azd-service-name': serviceName })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identityId}': {} }
  }
  properties: {
    environmentId: environmentId
    configuration: {
      activeRevisionsMode: 'Single'
      registries: [{ server: registryServer, identity: identityId }]
      secrets: secrets
      ingress: ingress == 'none' ? null : {
        external: ingress == 'external'
        targetPort: 8000
        transport: 'auto'
        allowInsecure: ingress == 'internal'
      }
    }
    template: {
      containers: [
        {
          name: role
          // azd replaces this placeholder with the built image on `azd deploy`.
          image: 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
          resources: { cpu: json(cpu), memory: memory }
          env: concat(env, [{ name: 'PITCHSIDE_ROLE', value: role }])
          probes: [
            {
              type: 'Liveness'
              httpGet: { path: '/api/health', port: 8000 }
              initialDelaySeconds: 20
              periodSeconds: 30
            }
          ]
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 1 }
    }
  }
}

output fqdn string = ingress == 'none' ? '' : app.properties.configuration.ingress.fqdn
output name string = app.name
