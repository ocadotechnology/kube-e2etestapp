# Troubleshooting errors
All errors for the test app are associated with a statsd counter named `e2etest.error.<resource>.<area>.<error>`. Each area is explained below, along with potential errors.
## API
The Kubernetes API has the potential to give several errors, listed and expanded below. 

### Bad Request
TODO - check when this happens
### Forbidden
This could potentially mean you're trying to do something illegal, like creating a resource in a namespace which is being deleted. 

### Not Found
Usually occurs when trying to read a resource which doesn't exist

### Conflict
Indicates trying to create a resource which has the same name as an existing object.

### Unprocessable entity
Attempt to create a resource which has invalid attributes.

### max_retries_exceeded
Given the Kubernetes API is a REST service, any requests to the API have the potential to be ignored, or the connection refused. In this case the Kubernetes python client will attempt to retry the connection, and may eventually hit the max number of retries.

## Timeout
The timeout area can occur when a method is waiting on Kubernetes events being created for a particular resource.
A timeout error indicates no events were created in the given amount of time (default time is 60 seconds). It can produce the following error values:
- `events`: indicates this error came from usage of _wait_on_event. Could be for any resource, generally indicates a resource was either never created or never terminated when we were expecting it to do so.
- `waiting_on_endpoints`: indicates this error came from service.watch_endpoints_till_correct. Meaning: enough service endpoint subsets were not created in time.
- `waiting_on_phase`: indicates this error came from deployment._wait_on_pods. Meaning: enough pods for a given deployment were not put into the right phase in time.

In any case, this probably means either the current test or a test it relies upon failed to work or was not deleted from a previous test run.

## K8s
Any test which fails a test may generate a k8s error. This indicates that the resource had some invalid or unexpected config. In this case the headers below are the full metric names as there are very few generic config problems.
### `namespace.k8s.not_empty`
This indicates some resource still exists in the namespace, probably indicating the creation test failed because the namespace was already there. If that's the case, there's probably also a `e2etest_errors.namespace.error.conflict` error counted.

### `pod.k8s.log_incorrect`
Indicates the log for one or more pods was not valid, either because there's no record of one or more requests happening or the log lines don't contain the right user agent.

### `pod.k8s.same_node`
Indicates pods weren't created on different nodes. Could mean enough nodes don't exist to split the pods amongst different nodes.

### `pod.k8s.same_data_centre`
Pods weren't created on different data centres. 

### `pod.k8s.no_zone_label_on_node`
During checking for the data centre, it was found the pod's node does not have a zone label, meaning it can't work out what data centre the pod is located in.

### `service.k8s.service_endpoint_count_wrong`
The count found when waiting for the service to create it's endpoint was wrong. May also have generated a timeout error. Probably due to backends (pods) not having been created or ready.

### `<resource>.k8s.not_deleted`
Resource should have been deleted but was not.
