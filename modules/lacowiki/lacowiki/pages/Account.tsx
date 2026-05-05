import '@simple-module-py/ui/lacowiki/styles.css';
import { WfAccount } from '@simple-module-py/ui/lacowiki/wf/account';

function LacoWikiAccount() {
  return (
    <div className="lw-app" data-density="normal">
      <main>
        <div className="eyebrow">Account</div>
        <h1 className="h-display">Account & settings.</h1>
        <p className="lede">Profile, workspaces, API tokens, notifications, billing.</p>
        <WfAccount />
      </main>
    </div>
  );
}

LacoWikiAccount.layout = (page: React.ReactNode) => page;

export default LacoWikiAccount;
