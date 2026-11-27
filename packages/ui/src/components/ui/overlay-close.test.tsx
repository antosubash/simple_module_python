import { configureI18n } from '@simple-module-py/i18n';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import de from '../../../../../framework/hosting/simple_module_hosting/ui_locales/de.json';
import en from '../../../../../framework/hosting/simple_module_hosting/ui_locales/en.json';
import es from '../../../../../framework/hosting/simple_module_hosting/ui_locales/es.json';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogTitle } from './dialog';
import { Sheet, SheetContent, SheetDescription, SheetTitle } from './sheet';

beforeEach(() => {
  configureI18n({ locale: 'en', messages: { 'ui.actions.close': en.actions.close } });
});

describe.each([
  {
    name: 'Sheet',
    Root: Sheet,
    Content: SheetContent,
    Title: SheetTitle,
    Description: SheetDescription,
  },
  {
    name: 'Dialog',
    Root: Dialog,
    Content: DialogContent,
    Title: DialogTitle,
    Description: DialogDescription,
  },
])('$name close button', ({ Root, Content, Title, Description }) => {
  it('has an always-on 44px minimum target around a 16px icon', () => {
    render(
      <Root open>
        <Content>
          <Title>Details</Title>
          <Description>Item details</Description>
        </Content>
      </Root>,
    );

    const button = screen.getByRole('button', { name: 'Close' });
    expect(button).toHaveClass(
      'min-h-11',
      'min-w-11',
      'inline-flex',
      'items-center',
      'justify-center',
    );
    expect(button.querySelector('svg')).toHaveClass('size-4');
  });

  it('merges caller sizing into the close button without forwarding it to the content', () => {
    render(
      <Root open>
        <Content closeButtonClassName="min-h-12 min-w-12 text-destructive">
          <Title>Details</Title>
          <Description>Item details</Description>
        </Content>
      </Root>,
    );

    const button = screen.getByRole('button', { name: 'Close' });
    expect(button).toHaveClass('min-h-12', 'min-w-12', 'text-destructive');
    expect(button).not.toHaveClass('min-h-11', 'min-w-11');
    expect(screen.getByRole('dialog')).not.toHaveAttribute('closeButtonClassName');
  });

  it('updates its accessible label when the locale changes', () => {
    render(
      <Root open>
        <Content>
          <Title>Details</Title>
          <Description>Item details</Description>
        </Content>
      </Root>,
    );

    expect(screen.getByRole('button', { name: 'Close' })).toBeInTheDocument();
    act(() => {
      configureI18n({ locale: 'de', messages: { 'ui.actions.close': de.actions.close } });
    });
    expect(screen.getByRole('button', { name: 'Schließen' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Close' })).not.toBeInTheDocument();
  });

  it('preserves dismissal and showCloseButton=false', () => {
    const onOpenChange = vi.fn();
    const { rerender } = render(
      <Root open onOpenChange={onOpenChange}>
        <Content>
          <Title>Details</Title>
          <Description>Item details</Description>
        </Content>
      </Root>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
    rerender(
      <Root open>
        <Content showCloseButton={false}>
          <Title>Details</Title>
          <Description>Item details</Description>
        </Content>
      </Root>,
    );
    expect(screen.queryByRole('button', { name: 'Close' })).not.toBeInTheDocument();
  });
});

it('translates the optional dialog footer close button', () => {
  configureI18n({ locale: 'es', messages: { 'ui.actions.close': es.actions.close } });
  render(
    <Dialog open>
      <DialogContent showCloseButton={false}>
        <DialogTitle>Details</DialogTitle>
        <DialogDescription>Item details</DialogDescription>
        <DialogFooter showCloseButton />
      </DialogContent>
    </Dialog>,
  );
  expect(screen.getByRole('button', { name: 'Cerrar' })).toBeInTheDocument();
});
