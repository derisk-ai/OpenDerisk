import { RouteItem } from './side-bar';
import ExpandLess from '@mui/icons-material/ExpandLess';
import ExpandMore from '@mui/icons-material/ExpandMore';
import Collapse from '@mui/material/Collapse';
import ListItemButton from '@mui/material/ListItemButton';
import cls from 'classnames';
import 'moment/locale/zh-cn';
import Link from 'next/link';
import { useEffect, useState } from 'react';

interface Tprops {
  value?: RouteItem;
  isStow?: boolean; // is close menu
}
const MenuList = (props: Tprops) => {
  const { value, isStow = false } = props;
  const { isActive = false } = value || {};
  const [open, setOpen] = useState(isActive);
  const handleClick = () => {
    setOpen(!open);
  };

  useEffect(() => {
    setOpen(isActive);
  }, [isActive]);

  return (
    <div>
      <ListItemButton
        onClick={handleClick}
        className={cls(
          'flex items-center w-full h-10 px-0 cursor-pointer hover:bg-[#F1F5F9] dark:hover:bg-theme-dark hover:rounded-md pl-2',
          isStow && 'hover:p-0',
        )}
      >
        {!isStow ? (
          <>
            <div className='mr-2 w-6 h-6'>{value?.icon}</div>
            <span className='text-sm'>{value?.name}</span>
          </>
        ) : (
          <>
            <Link key={value?.key} className={cls('h-10 flex items-center')} href={value?.path ?? '#'}>
              {value?.icon}
            </Link>
          </>
        )}
        {open ? <ExpandLess /> : <ExpandMore />}
      </ListItemButton>
      <Collapse in={open} timeout='auto' unmountOnExit>
        <div className='flex flex-col ml-10 mt-1 items-center'>
          {value?.children?.map((item: RouteItem) => {
            if (item?.hideInMenu) return <></>;
            if (!isStow) {
              return (
                <Link
                  href={item?.path || '#'}
                  className={cls(
                    'flex items-center w-full h-9 cursor-pointer hover:bg-[#F1F5F9] dark:hover:bg-theme-dark hover:rounded-md pl-2',
                    {
                      'bg-white rounded-md dark:bg-black': item.isActive,
                    },
                  )}
                  key={item.key}
                >
                  <div className={cls('mr-2', item?.isActive && 'text-cyan-500')}>{item.icon}</div>
                  <span className='text-[12px] text-black'>{item.name}</span>
                </Link>
              );
            }

            return (
              <Link
                key={item.key}
                className={cls('h-12 flex items-center', 'mr-3', item?.isActive && 'text-cyan-500')}
                href={item?.path || '#'}
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
