@description('Existing Cosmos DB account that stores public demo artifacts.')
param cosmosAccountName string

@description('Managed identity principal that refreshes public demo artifacts.')
param principalId string

resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' existing = {
  name: cosmosAccountName
}

resource publicDemoCosmosRole 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-05-15' = {
  parent: cosmos
  name: guid(cosmos.id, principalId, 'public-demo-data-contributor')
  properties: {
    principalId: principalId
    roleDefinitionId: '${cosmos.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002'
    scope: cosmos.id
  }
}
