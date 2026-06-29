import type { ContainerRow } from "../types";
import type { DataColumn } from "../ui";
import { PageHeader } from "../components/PageHeader";
import { RuntimeContainersPanel } from "./runtime/RuntimeContainersPanel";

type Props = {
  containerColumns: DataColumn<ContainerRow>[];
  containers: ContainerRow[];
};

export function RuntimeContainersPage({ containerColumns, containers }: Props) {
  return (
    <>
      <PageHeader title="Runtime Containers" />
      <RuntimeContainersPanel containerColumns={containerColumns} containers={containers} />
    </>
  );
}
