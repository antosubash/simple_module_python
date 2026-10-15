import { keys, useT } from '@simple-module-py/i18n';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@simple-module-py/ui/components/ui/table';
import { ROUTE_OVERRIDE_SOURCE, type TaskRoute } from '../constants';

/**
 * The effective task routes: which queue each pattern is sent to and who set
 * it. Routes live in module `task_config.py` files plus an operator override,
 * so without this table the only way to learn where a task goes is to read
 * every installed module's source.
 */
export function RoutesTable({ routes }: { routes: TaskRoute[] }) {
  const { t } = useT();
  return (
    <section className="mt-6 flex flex-col gap-2.5">
      <h2 className="text-[15px] font-bold font-display">
        {t(keys.background_tasks.workers.routes_title)}
      </h2>
      <p className="text-[13px] text-muted-foreground">
        {t(keys.background_tasks.workers.routes_description)}
      </p>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t(keys.background_tasks.workers.routes_pattern)}</TableHead>
            <TableHead>{t(keys.background_tasks.workers.routes_queue)}</TableHead>
            <TableHead>{t(keys.background_tasks.workers.routes_module)}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {routes.map((route) => (
            <TableRow key={route.pattern}>
              <TableCell className="font-mono text-xs">{route.pattern}</TableCell>
              <TableCell className="font-mono text-xs">
                {route.queue || t(keys.background_tasks.workers.routes_default_queue)}
              </TableCell>
              <TableCell>
                {route.module === ROUTE_OVERRIDE_SOURCE
                  ? t(keys.background_tasks.workers.routes_override)
                  : route.module}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </section>
  );
}
