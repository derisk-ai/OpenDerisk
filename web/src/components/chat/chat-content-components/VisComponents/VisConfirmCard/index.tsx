import React, { useState, useContext } from 'react';
import { VisConfirmCardWrap } from './style';
import {
  codeComponents,
  type MarkdownComponent,
  markdownPlugins,
} from '../../config';
import { GPTVis } from '@antv/gpt-vis';
import { Button, Divider, Space, Input, message } from 'antd';
import { CheckCircleOutlined } from '@ant-design/icons';
import { ChatContentContext } from '@/contexts';

interface QuestionOption {
  label: string;
  description?: string;
  value?: string;
  requires_input?: boolean;
  input_placeholder?: string;
  input_required?: boolean;
}

interface Question {
  question: string;
  header?: string;
  options?: QuestionOption[];
  multiple?: boolean;
}

interface VisConfirmIProps {
  data: {
    markdown?: string;
    disabled?: boolean;
    extra?: {
      confirm_type?: 'confirm' | 'select' | 'input';
      confirm_message?: string;
      options?: QuestionOption[];
      default_value?: string;
      placeholder?: string;
      approval_message_id?: string;
      questions?: Question[];
      header?: string;
      original_message_id?: string;
      multiple?: boolean;
      uid?: string;
      message_id?: string;
    };
    // Structured questions support (new)
    questions?: Question[];
    header?: string;
    request_id?: string;
    allow_custom_input?: boolean;
  };
  otherComponents?: MarkdownComponent;
  onConfirm?: (extra: unknown) => void;
}

/**
 * Build the user message with system_reminder wrapping
 */
const buildConfirmUserMessage = (
  confirmType: 'confirm' | 'select' | 'input',
  question: string,
  selectedOption: string | null,
  inputValue: string,
  options: QuestionOption[],
  hasQuestions: boolean,
  questions?: Question[],
  isCustomInputMode?: boolean,
  hasOptionInput?: boolean,
): string => {
  let questionText = question;
  let headerText = '';
  if (hasQuestions && questions && questions.length > 0) {
    const primaryQuestion = questions[0];
    questionText = primaryQuestion.question;
    headerText = primaryQuestion.header || '';
  }

  let msg = '<system_reminder>\n';
  msg += '【User Confirmation Response】\n\n';

  if (headerText) {
    msg += `**${headerText}**\n\n`;
  }

  if (questionText) {
    msg += `User has responded to the following question:\n**Question**: ${questionText}\n\n`;
  }

  if (confirmType === 'select') {
    if (isCustomInputMode && inputValue.trim()) {
      msg += `**User chose custom input**: ${inputValue.trim()}\n\n`;
    } else {
      const selectedOpt = options.find(
        (o) => o.label === selectedOption || o.value === selectedOption,
      );
      if (selectedOpt) {
        msg += `**User selected**: ${selectedOpt.label}`;
        if (selectedOpt.description) {
          msg += ` - ${selectedOpt.description}`;
        }
        msg += '\n\n';

        if (hasOptionInput && inputValue.trim()) {
          msg += `**Additional notes**: ${inputValue.trim()}\n\n`;
        }
      } else if (selectedOption) {
        msg += `**User selected**: ${selectedOption}\n\n`;
      }
    }
  } else if (confirmType === 'input') {
    msg += `**User reply**: ${inputValue.trim()}\n\n`;
  } else {
    msg += '**User confirmed**\n\n';
  }

  msg +=
    '**Important**: User has completed confirmation. Please proceed based on the user\'s selection. Do not ask the same question again.\n';
  msg += '</system_reminder>';

  return msg;
};

/**
 * Build the drsk-confirm-response display message
 */
const buildConfirmResponseDisplayMessage = (
  confirmType: 'confirm' | 'select' | 'input',
  question: string,
  selectedOption: string | null,
  inputValue: string,
  options: QuestionOption[],
  hasQuestions: boolean,
  questions?: Question[],
  isCustomInputMode?: boolean,
  hasOptionInput?: boolean,
): string => {
  const timestamp = new Date().toISOString();

  let questionText = question;
  let headerText = '';
  if (hasQuestions && questions && questions.length > 0) {
    const primaryQuestion = questions[0];
    questionText = primaryQuestion.question;
    headerText = primaryQuestion.header || '';
  }

  const responseData: Record<string, unknown> = {
    confirm_type: confirmType,
    question: questionText,
    header: headerText,
    timestamp,
  };

  if (confirmType === 'select') {
    if (isCustomInputMode) {
      responseData.input_content = inputValue.trim();
    } else {
      const selectedOpt = options.find(
        (o) => o.label === selectedOption || o.value === selectedOption,
      );
      if (selectedOpt) {
        responseData.selected_option = {
          label: selectedOpt.label,
          description: selectedOpt.description,
        };
        if (hasOptionInput && inputValue.trim()) {
          responseData.input_content = inputValue.trim();
        }
      } else if (selectedOption) {
        responseData.selected_option = { label: selectedOption };
      }
    }
  } else if (confirmType === 'input') {
    responseData.input_content = inputValue.trim();
  }

  return `\`\`\`drsk-confirm-response\n${JSON.stringify(responseData, null, 2)}\n\`\`\``;
};

const VisConfirmCard: React.FC<VisConfirmIProps> = ({ data, otherComponents, onConfirm }) => {
  const [disabled, setDisabled] = useState<boolean>(!!data.disabled);
  const [selectedOption, setSelectedOption] = useState<string | null>(null);
  const [inputValue, setInputValue] = useState<string>('');
  const [optionInputValue, setOptionInputValue] = useState<string>('');
  const [submitting, setSubmitting] = useState(false);
  const [isCustomInputMode, setIsCustomInputMode] = useState<boolean>(false);

  const { handleChat, appInfo, scrollRef } = useContext(ChatContentContext);

  const extra = data.extra || {};

  // Support both top-level questions and extra.questions
  const questions: Question[] = data.questions || extra.questions || [];
  const hasQuestions = questions.length > 0;
  const allowCustomInput = data.allow_custom_input !== false;

  let confirmType: 'confirm' | 'select' | 'input' = 'confirm';
  let confirmMessage = '';
  let options: QuestionOption[] = [];
  let placeholder = '';

  if (hasQuestions) {
    const primaryQuestion = questions[0];
    confirmMessage = primaryQuestion.question || data.header || extra.header || 'Needs your confirmation';
    options = primaryQuestion.options || [];
    confirmType = options.length > 0 ? 'select' : 'input';
    placeholder = 'Type your reply...';
  } else {
    confirmType = extra.confirm_type || 'confirm';
    confirmMessage = extra.confirm_message || 'Please confirm';
    options = extra.options || [];
    placeholder = extra.placeholder || 'Type your reply...';
  }

  const selectedOptionData = options.find(
    (o) => o.label === selectedOption || o.value === selectedOption,
  );
  const showOptionInput = selectedOptionData?.requires_input && !isCustomInputMode;

  const handleConfirm = async () => {
    if (disabled) return;

    let rawValue: string | null = null;
    let selectedOpt: QuestionOption | undefined;
    let finalInputValue = '';
    const actualConfirmType = isCustomInputMode ? 'input' : confirmType;

    switch (confirmType) {
      case 'select':
        if (isCustomInputMode) {
          if (!inputValue.trim()) {
            message.warning('Please enter custom content');
            return;
          }
          rawValue = inputValue.trim();
          finalInputValue = inputValue.trim();
        } else {
          if (!selectedOption) {
            message.warning('Please select an option');
            return;
          }
          rawValue = selectedOption;
          selectedOpt = options.find(
            (o) => o.label === selectedOption || o.value === selectedOption,
          );

          if (selectedOpt?.requires_input) {
            if (selectedOpt.input_required !== false && !optionInputValue.trim()) {
              message.warning('Please provide additional information');
              return;
            }
            finalInputValue = optionInputValue.trim();
          }
        }
        break;

      case 'input':
        if (!inputValue.trim()) {
          message.warning('Please enter content');
          return;
        }
        rawValue = inputValue.trim();
        finalInputValue = inputValue.trim();
        break;

      case 'confirm':
        rawValue = 'confirmed';
        break;
    }

    const userMessage = buildConfirmUserMessage(
      confirmType,
      confirmMessage,
      selectedOption,
      finalInputValue || inputValue,
      options,
      hasQuestions,
      questions,
      isCustomInputMode,
      selectedOpt?.requires_input,
    );

    setSubmitting(true);

    try {
      // Submit to interaction API to unblock gateway's send_and_wait()
      const requestId = data.request_id || extra.original_message_id || extra.approval_message_id;
      if (requestId) {
        try {
          const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || '';
          await fetch(`${apiBaseUrl}/api/v1/interaction/respond`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              request_id: requestId,
              choice: selectedOption || undefined,
              input_value: finalInputValue || inputValue || undefined,
              user_message: userMessage,
              metadata: {
                confirm_type: actualConfirmType,
                is_custom_input: isCustomInputMode,
              },
            }),
          });
        } catch (interactionError) {
          console.warn('Interaction API call failed (non-critical):', interactionError);
        }
      }

      if (handleChat) {
        await handleChat(userMessage, {
          app_code: appInfo?.app_code || '',
          original_message_id:
            data.request_id || extra.original_message_id || extra.approval_message_id || extra.message_id,
          display_metadata: {
            confirm_type: actualConfirmType,
            question: confirmMessage,
            selected_option: selectedOpt,
            input_content: finalInputValue || undefined,
            is_custom_input: isCustomInputMode,
            timestamp: new Date().toISOString(),
          },
        });
        setDisabled(true);
        message.success('Submitted, continuing execution...');

        setTimeout(() => {
          scrollRef?.current?.scrollTo({
            top: scrollRef.current?.scrollHeight,
            behavior: 'smooth',
          });
        }, 100);
      } else {
        // Fallback: use legacy onConfirm
        onConfirm?.(data?.extra ?? {});
        setDisabled(true);
        message.info('Selection recorded');
      }
    } catch (error) {
      console.error('Failed to submit response:', error);
      message.error('Submit failed, please try again');
    } finally {
      setSubmitting(false);
    }
  };

  const renderSelectOptions = () => {
    if (options.length === 0) return null;

    return (
      <div style={{ marginTop: 16, marginBottom: 16 }}>
        <div style={{ fontWeight: 500, marginBottom: 12, color: '#1890ff' }}>
          {hasQuestions ? confirmMessage : 'Please select:'}
        </div>
        <Space direction="vertical" style={{ width: '100%' }}>
          {options.map((opt, idx) => {
            const isSelected = selectedOption === (opt.value || opt.label);
            const shouldShowInput = isSelected && opt.requires_input;

            return (
              <div key={idx} style={{ width: '100%' }}>
                <Button
                  type={isSelected ? 'primary' : 'default'}
                  block
                  onClick={() => {
                    setSelectedOption(opt.value || opt.label);
                    setIsCustomInputMode(false);
                    setOptionInputValue('');
                  }}
                  disabled={disabled}
                  style={{
                    textAlign: 'left',
                    height: 'auto',
                    padding: '12px 16px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                  }}
                >
                  <span>
                    <strong>{opt.label}</strong>
                    {opt.description && (
                      <span style={{ color: '#666', marginLeft: 8, fontSize: 14 }}>
                        - {opt.description}
                      </span>
                    )}
                    {opt.requires_input && (
                      <span style={{ color: '#1890ff', marginLeft: 4, fontSize: 12 }}>
                        (can add notes)
                      </span>
                    )}
                  </span>
                  {isSelected && <CheckCircleOutlined />}
                </Button>

                {shouldShowInput && (
                  <div style={{ marginTop: 8, paddingLeft: 16 }}>
                    <Input.TextArea
                      value={optionInputValue}
                      onChange={(e) => setOptionInputValue(e.target.value)}
                      placeholder={opt.input_placeholder || 'Please provide additional details...'}
                      disabled={disabled}
                      rows={2}
                      style={{ fontSize: 14 }}
                    />
                  </div>
                )}
              </div>
            );
          })}
          {allowCustomInput && (
            <Button
              key="custom-input"
              type={isCustomInputMode ? 'primary' : 'default'}
              block
              onClick={() => {
                setIsCustomInputMode(true);
                setSelectedOption(null);
                setOptionInputValue('');
              }}
              disabled={disabled}
              style={{
                textAlign: 'left',
                height: 'auto',
                padding: '12px 16px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                borderStyle: 'dashed',
              }}
            >
              <span>
                <strong>Custom input</strong>
                <span style={{ color: '#666', marginLeft: 8, fontSize: 14 }}>
                  - Type your own response
                </span>
              </span>
              {isCustomInputMode && <CheckCircleOutlined />}
            </Button>
          )}
        </Space>
        {isCustomInputMode && (
          <Input.TextArea
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder="Type your custom content..."
            disabled={disabled}
            rows={3}
            style={{ marginTop: 12 }}
          />
        )}
      </div>
    );
  };

  const renderInput = () => {
    return (
      <div style={{ marginTop: 16, marginBottom: 16 }}>
        <div style={{ fontWeight: 500, marginBottom: 12, color: '#1890ff' }}>
          {hasQuestions ? confirmMessage : 'Please enter:'}
        </div>
        <Input.TextArea
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          placeholder={placeholder}
          disabled={disabled}
          rows={3}
          style={{ marginBottom: 12 }}
        />
      </div>
    );
  };

  const renderConfirmButton = () => {
    if (disabled) {
      return (
        <div style={{ color: '#52c41a', display: 'flex', alignItems: 'center' }}>
          <CheckCircleOutlined style={{ marginRight: 8 }} />
          Confirmed, Agent is processing...
        </div>
      );
    }

    let buttonText = 'Confirm';
    let isDisabled = false;

    if (confirmType === 'select') {
      if (isCustomInputMode) {
        buttonText = 'Submit Reply';
        isDisabled = !inputValue.trim();
      } else if (selectedOptionData?.requires_input) {
        buttonText = 'Confirm Selection';
        isDisabled = selectedOptionData.input_required !== false && !optionInputValue.trim();
      } else {
        buttonText = 'Confirm Selection';
        isDisabled = !selectedOption;
      }
    } else if (confirmType === 'input') {
      buttonText = 'Submit Reply';
      isDisabled = !inputValue.trim();
    }

    return (
      <Button
        type="primary"
        loading={submitting}
        disabled={isDisabled}
        style={{
          backgroundImage: 'linear-gradient(104deg, #3595ff 13%, #185cff 99%)',
          color: '#ffffff',
        }}
        onClick={handleConfirm}
      >
        {buttonText}
      </Button>
    );
  };

  const cardTitle = hasQuestions ? 'Needs your confirmation' : 'Confirm Action';

  return (
    <VisConfirmCardWrap className="VisConfirmCardClass">
      <div className="card-content">
        <span className="confirm-title">{cardTitle}</span>
        <Divider
          style={{
            margin: '8px 0px 8px 0px',
            borderWidth: '1px',
            borderColor: 'rgba(0, 0, 0, 0.03)',
          }}
        />
        <div className="whitespace-normal">
          {/* @ts-ignore */}
          <GPTVis
            className="whitespace-normal"
            components={{ ...codeComponents, ...(otherComponents || {}) }}
            {...markdownPlugins}
          >
            {data?.markdown || '-'}
          </GPTVis>
        </div>

        {confirmType === 'select' && renderSelectOptions()}
        {confirmType === 'input' && renderInput()}

        <Divider
          style={{
            margin: '8px 0px 8px 0px',
            borderWidth: '1px',
            borderColor: 'rgba(0, 0, 0, 0.03)',
          }}
        />
        <div className="confirm-footer">{renderConfirmButton()}</div>
      </div>
    </VisConfirmCardWrap>
  );
};

export default VisConfirmCard;
