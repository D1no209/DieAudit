param(
    [string]$Name = "bootstrap-admin",
    [string[]]$Scope = @("admin"),
    [string]$MetadataJson = "{}",
    [switch]$Json
)

$ErrorActionPreference = "Stop"

$argsList = @(
    "compose",
    "exec",
    "-T",
    "web-api",
    "python",
    "-m",
    "app.cli.create_api_key",
    "--name",
    $Name,
    "--metadata-json",
    $MetadataJson
)

foreach ($item in $Scope) {
    $argsList += @("--scope", $item)
}

if ($Json) {
    $argsList += "--json"
}

& docker @argsList
