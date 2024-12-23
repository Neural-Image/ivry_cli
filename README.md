### start server
`project-x start model --upload-url=http://localhost:3010/upload_file`

### prediction call
```
{
  "input": {
    "image": "http://localhost:3010/upload/upTAgMAHQe2SJTPy0UKUhA.jpeg",
    "prompt": "hello",
    "steps": 50,
    "guidance_scale": 5
  },
  "id": "string",
  "created_at": "2024-12-06T00:20:04.185Z",
  "webhook": "http://localhost:3010/webhook/prediction",
  "webhook_events_filter": [
    "start",
    "output",
    "logs",
    "completed"
  ]
}
```