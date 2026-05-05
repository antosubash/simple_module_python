import { Chrome } from '../chrome';
import { Btn, Frame, Stack } from '../primitives';
import { ReviewersCard, SourceCard, SummarySidebar, WorkflowCard } from './validation-create-cards';

export const WfValidationCreate = () => (
  <Frame name="11b · Create validation campaign" dim="1280×800">
    <div style={{ height: 560 }}>
      <Chrome
        active="Validation"
        title="New validation campaign"
        crumbs={['Validation']}
        actions={
          <>
            <Btn>Cancel</Btn>
            <Btn kind="primary">Create campaign</Btn>
          </>
        }
      >
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 16, height: '100%' }}>
          <Stack gap={12}>
            <SourceCard />
            <WorkflowCard />
            <ReviewersCard />
          </Stack>
          <SummarySidebar />
        </div>
      </Chrome>
    </div>
  </Frame>
);
