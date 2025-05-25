import { RouteItem } from '@/components/layout/side-bar';
import ExpandLess from '@mui/icons-material/ExpandLess';
import ExpandMore from '@mui/icons-material/ExpandMore';
import Collapse from '@mui/material/Collapse';
import ListItemButton from '@mui/material/ListItemButton';
import cls from 'classnames';
import 'moment/locale/zh-cn';
import Link from 'next/link';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

interface Tprops {
  value?: RouteItem;
  isStow?: boolean; // is close menu
}
const MenuList = (props: Tprops) => {
  const { value, isStow = false } = props;
  const { t } = useTranslation();
  const [open, setOpen] = useState(true);

  const handleClick = () => {
    setOpen(!open);
  };

  return (
    <div>
      <ListItemButton
        onClick={handleClick}
        className={cls(
          'flex items-center w-full h-12 px-4 cursor-pointer hover:bg-[#F1F5F9] dark:hover:bg-theme-dark hover:rounded-xl',
          isStow && 'hover:p-0',
        )}
      >
        {!isStow ? (
          <>
            <div className='mr-3'>{value?.icon}</div>
            {/* <ListItemText primary={value?.name} /> */}
            <span className='text-sm'>{t(value?.name as any)}</span>
          </>
        ) : (
          <>
            <Link key={value?.key} className={cls('h-12 flex items-center')} href={value?.path}>
              {value?.icon}
            </Link>
          </>
        )}
        {open ? <ExpandLess /> : <ExpandMore />}
      </ListItemButton>
      <Collapse in={open} timeout='auto' unmountOnExit>
        <div className='flex flex-col gap-4 ml-3 mt-3 items-center'>
          {value?.children?.map((item: RouteItem) => {
            if (item?.hideInMenu) return <></>;
            if (!isStow) {
              return (
                <Link
                  href={item?.path}
                  className={cls(
                    'flex items-center w-full h-12 px-4 cursor-pointer hover:bg-[#F1F5F9] dark:hover:bg-theme-dark hover:rounded-xl',
                    {
                      'bg-white rounded-xl dark:bg-black': item.isActive,
                    },
                  )}
                  key={item.key}
                >
                  <div className={cls('mr-3', item?.isActive && 'text-cyan-500')}>{item.icon}</div>
                  <span className='text-sm'>{t(item.name as any)}</span>
                </Link>
              );
            }

            return (
              <Link
                key={item.key}
                className={cls('h-12 flex items-center', 'mr-3', item?.isActive && 'text-cyan-500')}
                href={item?.path}
              >
                {item?.icon}
              </Link>
            );
          })}
        </div>
      </Collapse>
    </div>
  );
};

export default MenuList;
