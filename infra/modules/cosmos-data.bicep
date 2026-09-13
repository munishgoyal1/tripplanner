@description('Globally unique name for the Cosmos DB account.')
param accountName string

@description('Azure region for the Cosmos DB account.')
param location string

@description('Environment database names hosted by this account.')
param databaseNames array

@description('''Shared throughput for each environment database, positionally
matching databaseNames. DERIVED -- see infra/billing-guardrails.json azure.cosmos,
written by scripts/derive_limits.py from the INR ceilings. Do not hand-tune: a
number raised here and nowhere else drifts from the budget it is meant to serve.
Cosmos rejects a shared database below 400 RU/s; the derivation clamps to that
floor (cosmosSizing.minimumRuPerSecond) and tests/test_limits_derivation.py
asserts it, since @minValue cannot decorate an array parameter.''')
param databaseThroughputs int[]

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

resource databases 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-05-15' = [for (databaseName, index) in databaseNames: {
  parent: account
  name: databaseName
  properties: {
    resource: {
      id: databaseName
    }
    options: {
      throughput: databaseThroughputs[index]
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

resource flightRecorderContainers 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = [for (databaseName, index) in databaseNames: {
  parent: databases[index]
  name: 'flight_recorder'
  properties: {
    resource: {
      id: 'flight_recorder'
      partitionKey: {
        paths: ['/user_id']
        kind: 'Hash'
      }
      // 180 days; matches _TTL in src/tripplanner/flight_recorder.py.
      defaultTtl: 15552000
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

// These three were previously created at runtime by
// storage_cosmos._container()'s create_container_if_not_exists, so they never
// appeared in any throughput plan even though trip_costs is the cost ledger's
// hot path. Declaring them keeps the provisioned container set equal to the one
// cosmosSizing.tripOpProfile prices.
resource tripCostsContainers 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = [for (databaseName, index) in databaseNames: {
  parent: databases[index]
  name: 'trip_costs'
  properties: {
    resource: {
      id: 'trip_costs'
      partitionKey: {
        paths: ['/user_id']
        kind: 'Hash'
      }
    }
  }
}]

resource alertEventsContainers 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = [for (databaseName, index) in databaseNames: {
  parent: databases[index]
  name: 'alert_events'
  properties: {
    resource: {
      id: 'alert_events'
      partitionKey: {
        paths: ['/user_id']
        kind: 'Hash'
      }
    }
  }
}]

resource productEventsContainers 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = [for (databaseName, index) in databaseNames: {
  parent: databases[index]
  name: 'product_events'
  properties: {
    resource: {
      id: 'product_events'
      partitionKey: {
        paths: ['/user_id']
        kind: 'Hash'
      }
      defaultTtl: 7776000
    }
  }
}]

output accountName string = account.name
output endpoint string = account.properties.documentEndpoint
output databaseNames array = [for (databaseName, index) in databaseNames: databases[index].name]
