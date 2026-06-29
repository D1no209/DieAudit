import type { ContainerRow } from "../../types";
import { Alert, DataTable, Panel, type DataColumn } from "../../ui";

type Props = {
  containerColumns: DataColumn<ContainerRow>[];
  containers: ContainerRow[];
};

export function RuntimeContainersPanel({ containerColumns, containers }: Props) {
  const retained = containers.filter((item) => item.State !== "removed" && item.db_status !== "removed");

  return (
    <div className="grid gap-4">
      {retained.length > 0 ? (
        <Alert
          tone="warning"
          title="Runtime containers are retained"
          description={`${retained.length} managed container(s) are still present. This is expected when retain_runtime_on_failure is enabled or a sandbox target is running.`}
        />
      ) : null}
      <Panel>
        <DataTable getRowKey={(row) => row.Id} columns={containerColumns} data={containers} pagination={false} />
      </Panel>
    </div>
  );
}
