targetScope = 'resourceGroup'

@description('Azure Managed Redis instance name.')
param redisName string

@description('Azure region for the Redis instance.')
param location string

@description('Azure Managed Redis SKU name.')
param skuName string = 'Balanced_B0'

resource redis 'Microsoft.Cache/redisEnterprise@2025-07-01' = {
  name: redisName
  location: location
  sku: {
    name: skuName
  }
  properties: {
    minimumTlsVersion: '1.2'
    highAvailability: 'Enabled'
    publicNetworkAccess: 'Enabled'
  }
}

resource redisDatabase 'Microsoft.Cache/redisEnterprise/databases@2025-07-01' = {
  parent: redis
  name: 'default'
  properties: {
    clientProtocol: 'Encrypted'
    port: 10000
    clusteringPolicy: 'NoCluster'
    accessKeysAuthentication: 'Enabled'
    redisVersion: '7.4'
    // A cache that refuses writes when full would surface as provider errors,
    // so the oldest keys are evicted instead.
    evictionPolicy: 'AllKeysLRU'
  }
}

output redisName string = redis.name
output redisHostName string = redis.properties.hostName
output redisPort int = redisDatabase.properties.port
