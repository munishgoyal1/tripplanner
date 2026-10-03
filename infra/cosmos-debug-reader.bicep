@description('Existing Cosmos account. This template never retrieves account keys.')
param cosmosAccountName string
param databaseName string
@description('Object ID of the dedicated debugging user or group, not the application identity.')
param principalId string

resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' existing = {
  name: cosmosAccountName
}

var containers = ['trips', 'users']
resource readers 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-05-15' = [for container in containers: {
  parent: cosmos
  name: guid(cosmos.id, databaseName, container, principalId, 'debug-data-reader')
  properties: {
    principalId: principalId
    roleDefinitionId: '${cosmos.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000001'
    scope: '${cosmos.id}/dbs/${databaseName}/colls/${container}'
  }
}]

output roleAssignmentIds array = [for (container, i) in containers: readers[i].id]
