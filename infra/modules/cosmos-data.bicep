@description('Globally unique name for the Cosmos DB account.')
param accountName string

@description('Azure region for the Cosmos DB account.')
param location string

@description('Environment database names hosted by this account.')
param databaseNames array

@description('Fixed shared throughput for each environment database.')
@minValue(400)
param databaseThroughput int = 400

resource account 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' = {
  name: accountName
  location: location
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    enableFreeTier: true
    consistencyPolicy: {
      defaultConsistencyLevel: 'Session'
    }
    locations: [
      {
        locationName: location
        failoverPriority: 0
        isZoneRedundant: false
      }
    ]
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: false
  }
}

resource databases 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-05-15' = [for databaseName in databaseNames: {
  parent: account
  name: databaseName
  properties: {
    resource: {
      id: databaseName
    }
    options: {
      throughput: databaseThroughput
    }
  }
}]

resource usersContainers 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = [for (databaseName, index) in databaseNames: {
  parent: databases[index]
  name: 'users'
  properties: {
    resource: {
      id: 'users'
      partitionKey: {
        paths: ['/user_id']
        kind: 'Hash'
      }
    }
  }
}]

resource tripsContainers 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = [for (databaseName, index) in databaseNames: {
  parent: databases[index]
  name: 'trips'
  properties: {
    resource: {
      id: 'trips'
      partitionKey: {
        paths: ['/user_id']
        kind: 'Hash'
      }
    }
  }
}]

// Traveller document details — extracted fields only, never an original file.
resource documentsContainers 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = [for (databaseName, index) in databaseNames: {
  parent: databases[index]
  name: 'documents'
  properties: {
    resource: {
      id: 'documents'
      partitionKey: {
        paths: ['/user_id']
        kind: 'Hash'
      }
    }
  }
}]

resource placesCacheContainers 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = [for (databaseName, index) in databaseNames: {
  parent: databases[index]
  name: 'places_cache'
  properties: {
    resource: {
      id: 'places_cache'
      partitionKey: {
        paths: ['/user_id']
        kind: 'Hash'
      }
    }
  }
}]

resource sharedTripsContainers 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = [for (databaseName, index) in databaseNames: {
  parent: databases[index]
  name: 'shared_trips'
  properties: {
    resource: {
      id: 'shared_trips'
      partitionKey: {
        paths: ['/user_id']
        kind: 'Hash'
      }
    }
  }
}]

resource toolCacheContainers 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = [for (databaseName, index) in databaseNames: {
  parent: databases[index]
  name: 'tool_cache'
  properties: {
    resource: {
      id: 'tool_cache'
      partitionKey: {
        paths: ['/user_id']
        kind: 'Hash'
      }
    }
  }
}]

resource auditContainers 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = [for (databaseName, index) in databaseNames: {
  parent: databases[index]
  name: 'audit_events'
  properties: {
    resource: {
      id: 'audit_events'
      partitionKey: {
        paths: ['/user_id']
        kind: 'Hash'
      }
      defaultTtl: 7776000
    }
  }
}]

resource providerUsageContainers 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = [for (databaseName, index) in databaseNames: {
  parent: databases[index]
  name: 'provider_usage'
  properties: {
    resource: {
      id: 'provider_usage'
      partitionKey: {
        paths: ['/user_id']
        kind: 'Hash'
      }
      defaultTtl: 7776000
    }
  }
}]

resource tripFeedbackContainers 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = [for (databaseName, index) in databaseNames: {
  parent: databases[index]
  name: 'trip_feedback'
  properties: {
    resource: {
      id: 'trip_feedback'
      partitionKey: {
        paths: ['/user_id']
        kind: 'Hash'
      }
    }
  }
}]

resource publicDemoRunsContainers 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = [for (databaseName, index) in databaseNames: {
  parent: databases[index]
  name: 'public_demo_runs'
  properties: {
    resource: {
      id: 'public_demo_runs'
      partitionKey: {
        paths: ['/user_id']
        kind: 'Hash'
      }
    }
  }
}]

output accountName string = account.name
output endpoint string = account.properties.documentEndpoint
output databaseNames array = [for (databaseName, index) in databaseNames: databases[index].name]
